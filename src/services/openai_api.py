from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from src.config.settings import settings
from typing import List, Optional
import httpx


class OpenAIService:
    """
    Service to interact with OpenAI API using LangChain.
    Encapsulates LangChain ChatOpenAI initialization and common methods.
    """

    def __init__(self):
        # Create HTTP client with UTF-8 encoding
        http_client = httpx.Client(
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=30.0
        )
        
        self.llm = ChatOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            temperature=0.7,
            http_client=http_client
        )

    def topic_by_firstmessage(self, input: str) -> str:
        """Generate a conversation topic based on the first message"""
        messages = [
            SystemMessage(content="Generate a concise conversation topic (max 5 words)."),
            HumanMessage(content=input)
        ]
        response = self.llm.invoke(messages)
        return response.content.strip()

    def chat_with_history(
        self,
        user_message: str,
        history: List[dict],
        system_prompt: Optional[str] = None,
        k: int = 10
    ) -> str:
        """
        Chat with conversation history.
        
        Args:
            user_message: The current user message
            history: List of message dicts with 'message_content', 'sender_role', and 'created_at'
            system_prompt: Optional system prompt to set the assistant's behavior
            k: Maximum number of recent messages to include from history
        
        Returns:
            The assistant's response content
        """
        messages = []
        
        # Add system prompt if provided
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        
        # Sort history by created_at and limit to k most recent messages
        sorted_history = sorted(
            history,
            key=lambda x: x.get('created_at') or '',
            reverse=False
        )[-k:]
        
        # Convert history to LangChain messages
        for msg in sorted_history:
            role = msg.get('sender_role', '').upper()
            content = msg.get('message_content', '')
            
            if role == 'USER':
                messages.append(HumanMessage(content=content))
            elif role == 'ASSISTANT':
                messages.append(AIMessage(content=content))
            elif role == 'SYSTEM':
                messages.append(SystemMessage(content=content))
        
        # Add current user message
        messages.append(HumanMessage(content=user_message))
        
        # Invoke LLM and return response
        response = self.llm.invoke(messages)
        return response.content.strip()

