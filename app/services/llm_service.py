"""
LLM Service - handles all OpenAI API interactions.

This service is responsible for:
- Chat completions
- Embeddings generation
- Model selection and configuration
- Rate limiting and error handling
"""

from typing import List, Dict, Any, Optional, Union
from openai import OpenAI

from app.config import Config
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


class LLMService:
    """
    Service for LLM operations using OpenAI API.
    
    Centralizes all LLM interactions to provide:
    - Consistent error handling
    - Model configuration management
    - Easy testing and mocking
    - Rate limiting (future)
    """
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize the LLM service.
        
        Parameters
        ----------
        api_key : str, optional
            OpenAI API key (defaults to Config.OPENAI_API_KEY)
        model : str, optional
            Default model to use (defaults to Config.OPENAI_MODEL)
        """
        self.api_key = api_key or Config.OPENAI_API_KEY
        self.default_model = model or Config.OPENAI_MODEL
        self.embedding_model = Config.EMBEDDING_MODEL
        self.default_temperature = Config.OPENAI_TEMPERATURE
        self.default_max_tokens = Config.OPENAI_MAX_TOKENS
        self.client: Optional[OpenAI] = None
        
        logger.info(f"LLMService initialized with model: {self.default_model}")
    
    def get_client(self) -> OpenAI:
        """Get or create OpenAI client (singleton pattern)."""
        if self.client is None:
            self.client = OpenAI(api_key=self.api_key)
        return self.client
    
    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 768,
        tools: Optional[List[Dict]] = None,
        tool_choice: Union[str, Dict] = "auto",
    ) -> Any:
        """
        Generate a chat completion.
        
        Supports both text and image messages. If messages contain images,
        automatically uses a vision-capable model.
        
        Parameters
        ----------
        messages : list
            List of message dicts with 'role' and 'content'
            Content can be:
            - String (text message)
            - List of dicts with 'type': 'text' or 'image_url' (multimodal)
        model : str, optional
            Model to use (defaults to self.default_model)
            If images are detected, will use vision-capable model
        temperature : float
            Sampling temperature (0-2)
        max_tokens : int
            Maximum tokens to generate
        tools : list, optional
            Tool definitions for function calling
        tool_choice : str or dict
            Tool choice strategy ("auto", "none", or specific tool)
            
        Returns
        -------
        Response object from OpenAI API
        """
        client = self.get_client()
        model_name = model or self.default_model
        
        # Check if messages contain images
        has_images = False
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                has_images = any(
                    isinstance(item, dict) and item.get("type") == "image_url"
                    for item in content
                )
                if has_images:
                    break
        
        # Use vision-capable model if images are present
        if has_images:
            # gpt-4o-mini supports vision, but gpt-4o is better
            if "gpt-4o-mini" in model_name:
                # Keep gpt-4o-mini (it supports vision)
                pass
            elif "gpt-4" not in model_name.lower():
                # If not a vision model, switch to gpt-4o-mini
                model_name = "gpt-4o-mini"
                logger.info(f"Switching to vision-capable model: {model_name}")
        
        try:
            kwargs = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            
            if tools is not None:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = tool_choice
            
            logger.debug(f"Chat completion request: model={model_name}, has_images={has_images}")
            response = client.chat.completions.create(**kwargs)
            logger.debug(f"Chat completion successful")
            return response
        except Exception as e:
            logger.error(f"LLMService chat_completion failed: {e}", exc_info=True)
            raise
    
    def chat_completion_text(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 768,
    ) -> str:
        """
        Generate a chat completion and return just the text content.
        
        Convenience method for simple text generation without tool calling.
        
        Returns
        -------
        str
            Generated text content
        """
        try:
            response = self.chat_completion(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            logger.error(f"LLMService chat_completion_text failed: {e}", exc_info=True)
            return "I'm having trouble reaching the AI model right now. Please try again."
    
    def generate_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        """
        Generate an embedding vector for text.
        
        Parameters
        ----------
        text : str
            Text to embed
        model : str, optional
            Embedding model to use (defaults to text-embedding-ada-002)
            
        Returns
        -------
        list of float
            Embedding vector (1536 dimensions for ada-002)
        """
        client = self.get_client()
        model_name = model or self.embedding_model
        
        try:
            response = client.embeddings.create(
                model=model_name,
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"LLMService generate_embedding failed: {e}", exc_info=True)
            raise
    
    def generate_embeddings_batch(
        self,
        texts: List[str],
        model: Optional[str] = None,
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in a single API call.
        
        More efficient than calling generate_embedding multiple times.
        
        Parameters
        ----------
        texts : list of str
            List of texts to embed
        model : str, optional
            Embedding model to use
            
        Returns
        -------
        list of list of float
            List of embedding vectors
        """
        client = self.get_client()
        model_name = model or self.embedding_model
        
        try:
            response = client.embeddings.create(
                model=model_name,
                input=texts,
            )
            return [record.embedding for record in response.data]
        except Exception as e:
            logger.error(f"LLMService generate_embeddings_batch failed: {e}", exc_info=True)
            raise
    
    def extract_facts(self, user_input: str) -> str:
        """
        Extract factual statements from user input.
        
        Helper method for memory management.
        
        Parameters
        ----------
        user_input : str
            User's message
            
        Returns
        -------
        str
            Extracted facts, one per line starting with 'FACT:', or 'None'
        """
        prompt = f"""
Extract factual personal statements from the following user input. 
Examples: name, age, location, job, preferences, relationships, hobbies, beliefs, or other memorable details.
Respond one per line, each starting with 'FACT:'.
Return 'None' if there's nothing to store.

User input: "{user_input}"
"""
        messages = [
            {"role": "system", "content": "You are a fact extractor for a psychology chatbot."},
            {"role": "user", "content": prompt},
        ]
        
        return self.chat_completion_text(
            messages=messages,
            model="gpt-3.5-turbo",
            temperature=0,
            max_tokens=100,
        )
    
    def summarize_facts(self, context_text: str) -> str:
        """
        Summarize a list of facts about a user.
        
        Helper method for memory management.
        
        Parameters
        ----------
        context_text : str
            Text containing multiple facts
            
        Returns
        -------
        str
            Summarized facts
        """
        messages = [
            {
                "role": "system",
                "content": "You are summarizing facts about a user to help a psychology chatbot remember important details."
            },
            {
                "role": "user",
                "content": f"Summarize these known facts about the user:\n\n{context_text}"
            },
        ]
        
        return self.chat_completion_text(
            messages=messages,
            model="gpt-3.5-turbo",
            max_tokens=150,
        )


# Singleton instance
_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Get the singleton LLM service instance."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service

