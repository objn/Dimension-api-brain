from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.language_models.chat_models import BaseChatModel
from src.config.settings import settings
from typing import List, Optional, Literal, Union
import httpx
import base64
import io
import logging

logger = logging.getLogger(__name__)


# Type alias for LLM providers
LLMProviderType = Literal["openai", "gemini", "anthropic"]


def _get_llm(provider: LLMProviderType = "openai", timeout: float = 30.0) -> BaseChatModel:
    """Get LLM instance based on provider. Use higher timeout for vision (e.g. 120.0)."""
    if provider == "openai":
        http_client = httpx.Client(
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=timeout
        )
        return ChatOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            temperature=0.7,
            http_client=http_client
        )
    
    elif provider == "gemini":
        return ChatGoogleGenerativeAI(
            google_api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            temperature=0.7
        )
    
    elif provider == "anthropic":
        return ChatAnthropic(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            temperature=0.7
        )
    
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


def extract_text_from_images_vision(
    images: List[Union[bytes, "io.BytesIO", "Image.Image"]],
    provider: LLMProviderType = "openai",
    system_prompt: Optional[str] = None,
    timeout: float = 120.0,
    single_page_prompt: bool = False,
) -> str:
    """
    Extract text from document images using a vision-capable LLM.
    Use for PDF pages (as images) when local OCR fails or is not available.
    Images can be PIL Image, bytes, or BytesIO.
    When single_page_prompt=True (OCR-style, one page), uses a per-page extraction prompt.
    """
    if not images:
        return ""
    try:
        from PIL import Image as PILImage
    except ImportError:
        raise ValueError("PIL (Pillow) is required for vision extraction")

    content_parts: List[dict] = []
    if system_prompt:
        content_parts.append({"type": "text", "text": system_prompt})
    if single_page_prompt and len(images) == 1:
        prompt_text = (
            "You are an OCR system. Extract ALL text from this single document page image. "
            "Preserve layout, paragraphs, lists, tables, and reading order. "
            "Return only the extracted text, no preamble or commentary."
        )
    else:
        prompt_text = (
            "Extract all text from these document images in order. "
            "Preserve structure (paragraphs, lists, tables) and order. Return only the extracted text, no preamble."
        )
    content_parts.append({"type": "text", "text": prompt_text})

    for i, img in enumerate(images):
        if hasattr(img, "save"):
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        elif isinstance(img, bytes):
            b64 = base64.b64encode(img).decode("utf-8")
        elif isinstance(img, io.BytesIO):
            b64 = base64.b64encode(img.getvalue()).decode("utf-8")
        else:
            continue
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"}
        })

    llm = _get_llm(provider, timeout=timeout)
    message = HumanMessage(content=content_parts)
    response = llm.invoke([message])
    return (response.content or "").strip()


def topic_by_firstmessage(message: str, provider: LLMProviderType = "openai", max_retries: int = 3) -> str:
    """Generate a conversation topic based on the first message"""
    llm = _get_llm(provider)
    
    for attempt in range(max_retries):
        # Adjust instruction based on attempt number
        if attempt == 0:
            instruction = "Create a concise conversation topic from the user's first sentence (no more than 10 words)."
        elif attempt == 1:
            instruction = "Generate a SHORT conversation topic (maximum 5 words). Be extremely brief."
        else:
            instruction = "Generate ONLY 3-5 words as a topic. No explanations, just the topic."
        
        messages = [
            SystemMessage(content=instruction),
            HumanMessage(content=message)
        ]
        
        response = llm.invoke(messages)
        topic = response.content.strip()
        
        # Check length - if valid, return immediately
        if len(topic) <= 255:
            return topic
    
    # Fallback: If all retries failed, truncate to 255 characters
    return topic[:252] + "..." if len(topic) > 255 else topic


def chat_with_history(
    user_message: str,
    history: List[dict],
    provider: LLMProviderType = "openai",
    system_prompt: Optional[str] = None,
    k: int = 10,
    topic: Optional[str] = None,
    max_reasoning_loops: int = 1,
) -> str:
    """
    Chat with conversation history.

    Args:
        user_message: The current user message
        history: List of message dicts with 'message_content', 'sender_role', and 'created_at'
        provider: LLM provider to use (openai, gemini, anthropic)
        system_prompt: Optional system prompt to set the assistant's behavior
        k: Maximum number of recent messages to include from history
        topic: Optional conversation topic to include when history has < 10 messages
        max_reasoning_loops: 1 = single response; 2+ = instruct model to reason step-by-step (up to N steps) before answering

    Returns:
        The assistant's response content
    """
    # When max_reasoning_loops > 1, prepend reasoning instruction so the model thinks step-by-step
    if max_reasoning_loops > 1:
        reasoning_instruction = (
            f"Reason step by step (up to {max_reasoning_loops} steps) before giving your final answer. "
            "You may put your reasoning in <reasoning>...</reasoning> and your final answer in <answer>...</answer>, "
            "or simply write your reasoning followed by your answer. "
        )
        system_prompt = (reasoning_instruction + "\n\n" + (system_prompt or "")).strip() or reasoning_instruction

    llm = _get_llm(provider)
    messages = []

    # Add system prompt if provided
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    
    # Add topic context when history has fewer than 10 messages
    if topic and len(history) < 10:
        messages.append(SystemMessage(content=f"Conversation topic: {topic}"))
    
    # Sort history by created_at and limit to k most recent messages
    sorted_history = sorted(
        history,
        key=lambda x: x.get('created_at') or '',
        reverse=False
    )[-k:]
    
    # Convert history to LangChain messages
    # Role mapping per AI Agent Operating Instructions:
    # - USER -> HumanMessage
    # - AGENT/ASSISTANT -> AIMessage  
    # - SYSTEM -> SystemMessage
    # - TOOL -> SystemMessage (tool outputs as context)
    for msg in sorted_history:
        role = msg.get('sender_role', '').upper()
        content = msg.get('message_content', '')
        
        if role == 'USER':
            messages.append(HumanMessage(content=content))
        elif role in ('ASSISTANT', 'AGENT'):
            messages.append(AIMessage(content=content))
        elif role == 'SYSTEM':
            messages.append(SystemMessage(content=content))
        elif role == 'TOOL':
            # Tool outputs are added as system context
            messages.append(SystemMessage(content=f"[Tool Output]\n{content}"))
    
    # Add current user message
    messages.append(HumanMessage(content=user_message))

    # Invoke LLM and return response
    response = llm.invoke(messages)
    return response.content.strip()


def chat_with_history_and_images(
    user_message: str,
    history: List[dict],
    images: List[Union[bytes, "io.BytesIO", "Image.Image"]],
    provider: LLMProviderType = "openai",
    system_prompt: Optional[str] = None,
    k: int = 10,
    topic: Optional[str] = None,
    max_reasoning_loops: int = 1,
    timeout: float = 120.0,
) -> str:
    """
    Multimodal chat with conversation history + attached images.

    - Images are sent to the LLM directly (vision-capable models/providers).
    - History is provided as text context.
    - user_message is included as text alongside images.
    """
    if not images:
        return chat_with_history(
            user_message=user_message,
            history=history,
            provider=provider,
            system_prompt=system_prompt,
            k=k,
            topic=topic,
            max_reasoning_loops=max_reasoning_loops,
        )

    # When max_reasoning_loops > 1, prepend reasoning instruction so the model thinks step-by-step
    if max_reasoning_loops > 1:
        reasoning_instruction = (
            f"Reason step by step (up to {max_reasoning_loops} steps) before giving your final answer. "
            "You may put your reasoning in <reasoning>...</reasoning> and your final answer in <answer>...</answer>, "
            "or simply write your reasoning followed by your answer. "
        )
        system_prompt = (reasoning_instruction + "\n\n" + (system_prompt or "")).strip() or reasoning_instruction

    # Sort history by created_at and limit to k most recent messages
    sorted_history = sorted(
        history,
        key=lambda x: x.get("created_at") or "",
        reverse=False,
    )[-k:]

    history_lines: List[str] = []
    for msg in sorted_history:
        role = (msg.get("sender_role", "") or "").upper()
        content = (msg.get("message_content") or "").strip()
        if not content:
            continue
        history_lines.append(f"{role}: {content}")

    content_parts: List[dict] = []
    if system_prompt:
        content_parts.append({"type": "text", "text": system_prompt})
    if topic and len(sorted_history) < 10:
        content_parts.append({"type": "text", "text": f"Conversation topic: {topic}"})
    if history_lines:
        content_parts.append({"type": "text", "text": "Conversation history:\n" + "\n".join(history_lines)})

    # Add the user message and the images
    content_parts.append({"type": "text", "text": user_message})

    for img in images:
        try:
            if hasattr(img, "save"):
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                mime = "image/png"
            elif isinstance(img, bytes):
                b64 = base64.b64encode(img).decode("utf-8")
                mime = "image/png"
            elif isinstance(img, io.BytesIO):
                b64 = base64.b64encode(img.getvalue()).decode("utf-8")
                mime = "image/png"
            else:
                continue
            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                }
            )
        except Exception:
            continue

    llm = _get_llm(provider, timeout=timeout)
    message = HumanMessage(content=content_parts)
    response = llm.invoke([message])
    return (response.content or "").strip()


def simple_chat(
    message: str,
    provider: LLMProviderType = "openai",
    system_prompt: Optional[str] = None
) -> str:
    """
    Simple chat without history.
    
    Args:
        message: The user message
        provider: LLM provider to use
        system_prompt: Optional system prompt
    
    Returns:
        The assistant's response content
    """
    llm = _get_llm(provider)
    messages = []
    
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    
    messages.append(HumanMessage(content=message))
    
    response = llm.invoke(messages)
    return response.content.strip()