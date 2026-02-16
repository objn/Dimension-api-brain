from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.language_models.chat_models import BaseChatModel
from src.config.settings import settings
from typing import List, Optional, Literal
import httpx


# Type alias for LLM providers
LLMProviderType = Literal["openai", "gemini", "anthropic"]


def _get_llm(provider: LLMProviderType = "openai") -> BaseChatModel:
    """Get LLM instance based on provider"""
    if provider == "openai":
        http_client = httpx.Client(
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=30.0
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


def topic_by_firstmessage(message: str, provider: LLMProviderType = "openai", max_retries: int = 3) -> str:
    """Generate a conversation topic based on the first message"""
    llm = _get_llm(provider)
    
    for attempt in range(max_retries):
        # Adjust instruction based on attempt number
        if attempt == 0:
            instruction = "Generate a concise conversation topic (max 10 words)."
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
    topic: Optional[str] = None
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
    
    Returns:
        The assistant's response content
    """
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