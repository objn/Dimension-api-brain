"""
Chat Service - Implements AI Agent Operating Instructions.

This service handles the multi-role conversation flow:
- Messages are immutable (append-only)
- Proper role assignment (SYSTEM, USER, AGENT, TOOL)
- Agent persona management via agent_prompt
- Context management with recent message filtering
"""
import logging
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from src.database.models import Messages, Conversations, Agents, Nodes, Files
from src.repositories.conversation_repository import ConversationRepository, MessageRepository
from src.repositories.agent_repository import AgentRepository
from src.repositories.node_repository import NodeRepository
from src.repositories.file_repository import FileRepository
from src.dto.conversation_dto import (
    SenderRole,
    MessageResponse,
    ChatResponse,
    ChatHistoryResponse,
    ChatPanelRequest,
    ChatPanelResponse,
    AgentPanelResponseItem,
    LLMProviderType
)
from src.services.rag import semantic_search_service
from src.services.document_parse_service import parse_document
import src.services.llm_router as LLM

# Hardcoded RAG/context limits (removed from API)
MAX_HISTORY = 10
# Default number of top chunks by similarity to retrieve when use_rag is true (select k best from node_vector)
RAG_TOP_K_DEFAULT = 5
# Lower similarity threshold for chat RAG so more chunks pass and citations are returned (0.7 often filters all)
RAG_MIN_SIMILARITY_CHAT = 0.3


class ChatService:
    """
    Chat service implementing AI Agent Operating Instructions.
    
    Conversation Model:
    - A Conversation is a container of context
    - A Message is an immutable event in the conversation timeline
    - Messages must never be edited or deleted, only appended
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.conversation_repo = ConversationRepository(db)
        self.message_repo = self.conversation_repo.get_message_repository()
        self.agent_repo = AgentRepository(db)
        self.node_repo = NodeRepository(db)
        self.file_repo = FileRepository(db)
    
    def _check_conversation_ownership(
        self,
        conversation_id: UUID,
        user_id: UUID
    ) -> Conversations:
        """
        Check if the user owns the conversation.
        Raises ValueError if conversation not found or user doesn't own it.
        """
        conversation = self.conversation_repo.find_one_by_id(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")
        
        if conversation.created_by != user_id:
            raise PermissionError("You don't have permission to access this conversation")
        
        return conversation
    
    def create_message(
        self,
        conversation_id: UUID,
        content: str,
        sender_role: SenderRole,
        created_by: UUID,
        metadatas: Optional[Dict[str, Any]] = None,
    ) -> Messages:
        """
        Create a new immutable message in the conversation.
        Messages are append-only - never edited or deleted.
        """
        new_message = Messages(
            message_id=uuid4(),
            conversation_id=conversation_id,
            message_content=content,
            sender_role=sender_role.value,
            metadatas=metadatas,
            created_by=created_by,
            created_at=datetime.utcnow(),
            updated_by=created_by,
            updated_at=datetime.utcnow()
        )
        return self.message_repo.create(new_message)
    
    def get_conversation_context(
        self,
        conversation_id: UUID,
        max_messages: int = 10,
        user_id: Optional[UUID] = None
    ) -> List[Dict[str, Any]]:
        """
        Get relevant recent messages for context.
        Filters and sorts by timestamp, returns most recent k messages.
        """
        # Check ownership if user_id provided
        if user_id:
            conversation = self._check_conversation_ownership(conversation_id, user_id)
        else:
            conversation = self.conversation_repo.find_one_by_id(conversation_id)
            if not conversation:
                return []
        
        # Get messages sorted by created_at
        messages = sorted(
            conversation.messages,
            key=lambda m: m.created_at or datetime.min
        )
        
        # Return most recent messages as context
        recent_messages = messages[-max_messages:] if len(messages) > max_messages else messages
        
        return [
            {
                "message_id": str(msg.message_id),
                "message_content": msg.message_content,
                "sender_role": msg.sender_role,
                "created_at": msg.created_at.isoformat() if msg.created_at else None
            }
            for msg in recent_messages
        ]
    
    def process_user_message(
        self,
        conversation_id: UUID,
        user_message: str,
        agent_id: UUID,
        user_id: UUID,
        llm_provider: LLMProviderType = "openai",
        use_rag: bool = False,
        workspace_id: Optional[UUID] = None,
        attach: Optional[Dict[str, Any]] = None,
        max_reasoning_loops: int = 1,
        rag_top_k: Optional[int] = None,
    ) -> ChatResponse:
        """
        Process a USER message and generate an AGENT response.

        Flow per AI Agent Operating Instructions:
        1. Read the latest conversation context
        2. Optionally run RAG search (by similarity, top-k chunks) and inject into context
        3. Apply agent_prompt and optional reasoning instruction
        4. Generate response (with optional step-by-step reasoning when max_reasoning_loops > 1)
        5. Store response as AGENT message; return with optional citations

        rag_top_k: number of top chunks by similarity to use when use_rag is true (default RAG_TOP_K_DEFAULT).
        max_reasoning_loops: 1 = single response; 2+ = instruct model to reason step-by-step up to that many steps.
        """
        attach = attach or {}
        attach_nodes: List[UUID] = list(attach.get("nodes") or [])
        attach_files: List[UUID] = list(attach.get("files") or [])
        attach_conversations: List[UUID] = list(attach.get("conversations") or [])
        k_chunks = rag_top_k if rag_top_k is not None else RAG_TOP_K_DEFAULT

        # Validate conversation exists and check ownership
        conversation = self._check_conversation_ownership(conversation_id, user_id)
        
        # Validate agent exists and get agent_prompt
        agent = self.agent_repo.find_one_by_id(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Use agent's default LLM provider when request did not specify one
        effective_provider: LLMProviderType = (
            getattr(agent, "default_llm_provider", None) or llm_provider or "openai"
        )
        if effective_provider not in ("openai", "gemini", "anthropic"):
            effective_provider = "openai"
        
        # 1. Store USER message (immutable)
        user_msg = self.create_message(
            conversation_id=conversation_id,
            content=user_message,
            sender_role=SenderRole.USER,
            created_by=user_id
        )
        
        # 2. Get conversation context (recent messages, hardcoded limit)
        context = self.get_conversation_context(conversation_id, MAX_HISTORY, user_id=user_id)
        
        # Resolve scope_node_ids: explicit attach.nodes else workspace nodes when use_rag + workspace_id
        scope_node_ids: Optional[List[UUID]] = None
        if attach_nodes:
            scope_node_ids = attach_nodes
        elif use_rag and workspace_id:
            scope_node_ids = self.node_repo.find_node_ids_by_workspace(workspace_id)
            if not scope_node_ids:
                scope_node_ids = None  # search unscoped if workspace has no nodes
        
        # Collect attachments per type for structured reference context
        citations: List[Dict[str, Any]] = []
        index = 1
        attached_images: List[bytes] = []
        image_names: List[str] = []
        node_parts: List[str] = []
        file_parts: List[str] = []
        convo_parts: List[str] = []
        rag_parts: List[str] = []

        # Collect attachment details for USER message metadatas (built inline)
        node_attachments: List[Dict[str, Any]] = []
        file_attachments: List[Dict[str, Any]] = []
        conversation_attachments: List[Dict[str, Any]] = []

        # ── Attached files ──────────────────────────────────────────────
        for file_id in attach_files:
            file_entity = self.file_repo.find_one_by_id(file_id)
            if not file_entity:
                logger.warning("Attach file %s: not found in database, skipping", file_id)
                continue

            fname = file_entity.file_name or "file"
            file_detail = {
                "file_id": str(file_entity.file_id),
                "file_name": fname,
                "file_size": file_entity.file_size,
                "mime_type": file_entity.mime_type or "",
            }
            file_attachments.append(file_detail)

            try:
                mime = (file_entity.mime_type or "").lower()

                if mime.startswith("image/") and file_entity.file_path:
                    with open(file_entity.file_path, "rb") as f:
                        img_bytes = f.read()
                    if img_bytes:
                        attached_images.append(img_bytes)
                        image_names.append(fname)
                        citations.append({
                            "index": index,
                            "source_type": "file",
                            "file": file_detail,
                            "snippet": f"[Image: {fname}]",
                        })
                        index += 1
                        logger.info("Attach file %s: image loaded (%d bytes)", file_id, len(img_bytes))
                    continue

                text = parse_document(
                    file_entity.file_path,
                    mime_type=file_entity.mime_type,
                    filename=file_entity.file_name,
                )
                if text and text.strip():
                    snippet = text.strip()[:300] + "…" if len(text.strip()) > 300 else text.strip()
                    file_parts.append(f"[{index}] File: \"{fname}\" (type: {file_entity.mime_type or 'unknown'})\n{text.strip()}")
                    citations.append({
                        "index": index,
                        "source_type": "file",
                        "file": file_detail,
                        "snippet": snippet,
                    })
                    index += 1
                    logger.info("Attach file %s: text extracted (%d chars)", file_id, len(text.strip()))
                else:
                    logger.warning("Attach file %s: parse_document returned empty text", file_id)
            except Exception as e:
                logger.error("Attach file %s: failed to process – %s", file_id, e, exc_info=True)

        # ── Attached nodes ──────────────────────────────────────────────
        for nid in attach_nodes:
            node = self.node_repo.find_one_by_id(nid)
            if not node:
                logger.warning("Attach node %s: not found in database, skipping", nid)
                continue

            nname = node.node_name or str(nid)
            node_attachments.append({
                "node_id": str(node.node_id),
                "node_name": nname,
                "node_desc": node.node_desc or "",
            })

            if not node.node_content_md:
                logger.warning("Attach node %s (%s): node_content_md is empty, skipping", nid, node.node_name)
                continue
            ndesc = f" – {node.node_desc}" if node.node_desc else ""
            snippet = (node.node_content_md.strip()[:300] + "…") if len(node.node_content_md.strip()) > 300 else node.node_content_md.strip()
            node_parts.append(f"[{index}] Node: \"{nname}\"{ndesc}\n{node.node_content_md.strip()}")
            citations.append({
                "index": index,
                "source_type": "node",
                "node": {
                    "node_id": str(node.node_id),
                    "node_name": nname,
                    "node_desc": node.node_desc or "",
                },
                "snippet": snippet,
            })
            index += 1

        # ── Attached conversations ──────────────────────────────────────
        for cid in attach_conversations:
            try:
                convo = self._check_conversation_ownership(cid, user_id)
            except (PermissionError, ValueError):
                logger.warning("Attach conversation %s: permission denied or not found, skipping", cid)
                continue

            conversation_attachments.append({
                "conversation_id": str(convo.conversation_id),
                "conversation_topic": convo.conversation_topic or "",
            })

            history = self.get_conversation_context(
                conversation_id=cid,
                max_messages=MAX_HISTORY,
                user_id=user_id,
            )
            if not history:
                continue

            lines: List[str] = []
            for msg in history:
                role = msg.get("sender_role", "USER")
                content = msg.get("message_content") or ""
                if not content:
                    continue
                lines.append(f"{role}: {content}")

            if not lines:
                continue

            convo_text = "\n".join(lines)
            snippet = convo_text[:300] + "…" if len(convo_text) > 300 else convo_text
            title = convo.conversation_topic or str(cid)

            convo_parts.append(f"[{index}] Conversation: \"{title}\"\n{convo_text}")
            citations.append({
                "index": index,
                "source_type": "conversation",
                "conversation": {
                    "conversation_id": str(convo.conversation_id),
                    "conversation_topic": convo.conversation_topic or "",
                },
                "snippet": snippet,
            })
            index += 1

        # ── RAG search (similarity) ────────────────────────────────────
        if use_rag:
            search_results = semantic_search_service.search(
                db=self.db,
                query_text=user_message,
                limit=k_chunks,
                scope_node_ids=scope_node_ids,
                min_similarity=RAG_MIN_SIMILARITY_CHAT,
            )
            if search_results:
                rag_node_ids = list({r.node_id for r in search_results})
                nodes_by_id: Dict[UUID, Nodes] = {}
                if rag_node_ids:
                    for n in self.node_repo.find_by_ids(rag_node_ids):
                        nodes_by_id[n.node_id] = n
                for r in search_results:
                    node_entity = nodes_by_id.get(r.node_id)
                    rname = (node_entity.node_name or str(r.node_id)) if node_entity else str(r.node_id)
                    rag_parts.append(f"[{index}] Related knowledge from \"{rname}\":\n{r.node_content_md_chunk}")
                    citations.append({
                        "index": index,
                        "source_type": "node",
                        "node": {
                            "node_id": str(r.node_id),
                            "node_name": rname,
                            "node_desc": (node_entity.node_desc or "") if node_entity else "",
                        },
                        "chunk_id": str(r.chunk_id),
                        "chunk_index": r.node_vector_chunk_order,
                        "snippet": (r.node_content_md_chunk[:200] + "…") if len(r.node_content_md_chunk) > 200 else r.node_content_md_chunk,
                        "similarity": r.similarity,
                    })
                    index += 1

        # ── Save attachments to USER message metadatas ──────────────────
        attachments: Dict[str, Any] = {
            "nodes": node_attachments,
            "files": file_attachments,
            "conversations": conversation_attachments,
        }
        if node_attachments or file_attachments or conversation_attachments:
            user_msg.metadatas = {"attachments": attachments}
            self.db.add(user_msg)
            self.db.flush()

        # ── Build structured reference context ──────────────────────────
        system_prompt = agent.agent_prompt or ""

        ref_sections: List[str] = []
        if image_names:
            names = ", ".join(f'"{n}"' for n in image_names)
            ref_sections.append(f"ATTACHED IMAGES (sent as visual input): {names}\nAnalyze the images provided and use them to answer the user's question.")
        if file_parts:
            ref_sections.append("ATTACHED FILES (text content extracted):\n" + "\n\n".join(file_parts))
        if node_parts:
            ref_sections.append("ATTACHED NOTES/NODES (knowledge base entries):\n" + "\n\n".join(node_parts))
        if convo_parts:
            ref_sections.append("ATTACHED CONVERSATIONS (previous chat history):\n" + "\n\n".join(convo_parts))
        if rag_parts:
            ref_sections.append("RELATED KNOWLEDGE (retrieved by similarity search):\n" + "\n\n".join(rag_parts))

        reference_context: Optional[str] = None
        if ref_sections:
            reference_context = (
                "IMPORTANT – The user has attached the following context to this message. "
                "You MUST read and use ALL of this information to answer their question. "
                "Cite sources by number [1], [2], etc.\n\n"
                + "\n\n---\n\n".join(ref_sections)
            )
            logger.info(
                "Reference context built: images=%d, files=%d, nodes=%d, conversations=%d, rag=%d",
                len(image_names), len(file_parts), len(node_parts), len(convo_parts), len(rag_parts),
            )
        
        # 4. Generate AGENT response (multimodal when images are attached)
        if attached_images:
            agent_response_content = LLM.chat_with_history_and_images(
                user_message=user_message,
                topic=conversation.conversation_topic,
                history=context,
                images=attached_images,
                provider=effective_provider,
                system_prompt=system_prompt,
                k=MAX_HISTORY,
                max_reasoning_loops=max_reasoning_loops,
                reference_context=reference_context,
            )
        else:
            agent_response_content = LLM.chat_with_history(
                user_message=user_message,
                topic=conversation.conversation_topic,
                history=context,
                provider=effective_provider,
                system_prompt=system_prompt,
                k=MAX_HISTORY,
                max_reasoning_loops=max_reasoning_loops,
                reference_context=reference_context,
            )
        
        # 5. Store AGENT response with agent_id (and citations when present) in metadatas
        agent_metadatas: Dict[str, Any] = {"agent_id": str(agent_id)}
        if citations:
            agent_metadatas["citations"] = citations
        agent_msg = self.create_message(
            conversation_id=conversation_id,
            content=agent_response_content,
            sender_role=SenderRole.AGENT,
            created_by=user_id,
            metadatas=agent_metadatas,
        )
        
        # Update conversation timestamp
        self.conversation_repo.update_by_id(conversation_id, {
            "updated_at": datetime.utcnow(),
            "updated_by": user_id
        })

        return ChatResponse(
            conversation_id=conversation_id,
            user_message=MessageResponse.model_validate(user_msg),
            agent_response=MessageResponse.model_validate(agent_msg),
            agent_id=agent_id,
            agent_name=agent.agent_name,
            messages_in_context=len(context),
        )
    
    def record_tool_output(
        self,
        conversation_id: UUID,
        tool_name: str,
        tool_output: str,
        tool_input: Optional[str],
        user_id: UUID
    ) -> Messages:
        """
        Record a TOOL message in the conversation.
        
        Per AI Agent Operating Instructions:
        - Store tool input/output as TOOL role message
        - This can then be used to generate final AGENT response
        """
        # Check ownership
        self._check_conversation_ownership(conversation_id, user_id)
        
        # Format tool message content
        content = f"[TOOL: {tool_name}]"
        if tool_input:
            content += f"\nInput: {tool_input}"
        content += f"\nOutput: {tool_output}"
        
        return self.create_message(
            conversation_id=conversation_id,
            content=content,
            sender_role=SenderRole.TOOL,
            created_by=user_id
        )
    
    def record_system_message(
        self,
        conversation_id: UUID,
        content: str,
        user_id: UUID,
        is_error: bool = False
    ) -> Messages:
        """
        Record a SYSTEM message in the conversation.
        
        Per AI Agent Operating Instructions:
        - SYSTEM messages are for notices, errors, policies, or hidden context
        - Errors should be reported as SYSTEM messages
        """
        # Check ownership
        self._check_conversation_ownership(conversation_id, user_id)
        
        if is_error:
            content = f"[ERROR] {content}"
        
        return self.create_message(
            conversation_id=conversation_id,
            content=content,
            sender_role=SenderRole.SYSTEM,
            created_by=user_id
        )
    
    def get_chat_history(
        self,
        conversation_id: UUID,
        user_id: Optional[UUID] = None
    ) -> ChatHistoryResponse:
        """
        Get full chat history with role-based statistics.
        """
        # Check ownership if user_id provided
        if user_id:
            conversation = self._check_conversation_ownership(conversation_id, user_id)
        else:
            conversation = self.conversation_repo.find_one_by_id(conversation_id)
            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")
        
        messages = sorted(
            conversation.messages,
            key=lambda m: m.created_at or datetime.min
        )
        
        # Calculate role counts
        role_counts = {
            SenderRole.USER.value: 0,
            SenderRole.AGENT.value: 0,
            SenderRole.SYSTEM.value: 0,
            SenderRole.TOOL.value: 0
        }
        for msg in messages:
            if msg.sender_role in role_counts:
                role_counts[msg.sender_role] += 1
        
        return ChatHistoryResponse(
            conversation_id=conversation_id,
            conversation_topic=conversation.conversation_topic,
            total_messages=len(messages),
            messages=[MessageResponse.model_validate(msg) for msg in messages],
            role_counts=role_counts
        )
    
    def respond_after_tool(
        self,
        conversation_id: UUID,
        agent_id: UUID,
        user_id: UUID,
        llm_provider: LLMProviderType = "openai",
        max_history: int = 10
    ) -> Messages:
        """
        Generate an AGENT response after a TOOL call.
        
        Per AI Agent Operating Instructions:
        - After recording TOOL output, agent should respond again as AGENT
        """
        # Check ownership
        self._check_conversation_ownership(conversation_id, user_id)
        
        agent = self.agent_repo.find_one_by_id(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        effective_provider: LLMProviderType = (
            getattr(agent, "default_llm_provider", None) or llm_provider or "openai"
        )
        if effective_provider not in ("openai", "gemini", "anthropic"):
            effective_provider = "openai"
        
        context = self.get_conversation_context(conversation_id, max_history)
        
        # Generate response with tool output in context
        agent_response = LLM.chat_with_history(
            user_message="Based on the tool output above, please provide a response.",
            history=context,
            provider=effective_provider,
            system_prompt=agent.agent_prompt,
            k=max_history
        )
        
        # created_by is the user who triggered, agent_id tracked separately
        return self.create_message(
            conversation_id=conversation_id,
            content=agent_response,
            sender_role=SenderRole.AGENT,
            created_by=user_id,
            metadatas={"agent_id": str(agent_id)},
        )

    def process_panel_message(
        self,
        conversation_id: UUID,
        user_message: str,
        agent_ids: List[UUID],
        user_id: UUID,
        llm_provider: LLMProviderType = "openai",
        max_history: int = 10,
    ):
        """
        Store one USER message, then get a response from each agent (sequential).
        Returns ChatPanelResponse with user_message and list of agent responses.
        """
        conversation = self._check_conversation_ownership(conversation_id, user_id)
        user_msg = self.create_message(
            conversation_id=conversation_id,
            content=user_message,
            sender_role=SenderRole.USER,
            created_by=user_id
        )
        context = self.get_conversation_context(conversation_id, max_history)
        agent_responses: List[AgentPanelResponseItem] = []
        for agent_id in agent_ids:
            agent = self.agent_repo.find_one_by_id(agent_id)
            if not agent:
                continue
            effective_provider: LLMProviderType = (
                getattr(agent, "default_llm_provider", None) or llm_provider or "openai"
            )
            if effective_provider not in ("openai", "gemini", "anthropic"):
                effective_provider = "openai"
            agent_content = LLM.chat_with_history(
                user_message=user_message,
                topic=conversation.conversation_topic,
                history=context,
                provider=effective_provider,
                system_prompt=agent.agent_prompt,
                k=max_history
            )
            agent_msg = self.create_message(
                conversation_id=conversation_id,
                content=agent_content,
                sender_role=SenderRole.AGENT,
                created_by=user_id,
                metadatas={"agent_id": str(agent_id)},
            )
            agent_responses.append(
                AgentPanelResponseItem(
                    agent_id=agent_id,
                    agent_name=agent.agent_name,
                    message=MessageResponse.model_validate(agent_msg),
                )
            )
        self.conversation_repo.update_by_id(conversation_id, {
            "updated_at": datetime.utcnow(),
            "updated_by": user_id
        })
        return ChatPanelResponse(
            conversation_id=conversation_id,
            user_message=MessageResponse.model_validate(user_msg),
            agent_responses=agent_responses,
        )
