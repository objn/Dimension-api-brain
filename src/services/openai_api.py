from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from src.config.settings import settings
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

    def send_text(self, input: str) -> str:
        """Generate text using LangChain's ChatOpenAI"""
        messages = [HumanMessage(content=input)]
        response = self.llm.invoke(messages)
        return response.content.strip()

    def web_search(self, input: str) -> str:
        """Note: Web search requires LangChain agents with search tools."""
        raise NotImplementedError("Web search requires LangChain agents with search tools implementation")