"""
OpenAI LLM client (chat + embeddings).

Env vars match ``backend.config.Config`` / production ``.env``.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Union

from openai import OpenAI

from backend.utils.logger import get_logger

logger = get_logger("llm_client")


def _env_str(key: str, default: str = "") -> str:
    return (os.getenv(key) or default).strip()


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


class LLMService:
    """OpenAI-backed LLM operations."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or _env_str("OPENAI_API_KEY")
        self.default_model = model or _env_str("OPENAI_MODEL", "gpt-4o-mini")
        self.embedding_model = _env_str("EMBEDDING_MODEL", "text-embedding-ada-002")
        self.default_temperature = _env_float("OPENAI_TEMPERATURE", 0.3)
        self.default_max_tokens = _env_int("OPENAI_MAX_TOKENS", 768)
        self.client: Optional[OpenAI] = None

        logger.info("LLMService initialized with model: %s", self.default_model)

    def get_client(self) -> OpenAI:
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
        client = self.get_client()
        model_name = model or self.default_model

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

        if has_images:
            if "gpt-4o-mini" in model_name:
                pass
            elif "gpt-4" not in model_name.lower():
                model_name = "gpt-4o-mini"
                logger.info("Switching to vision-capable model: %s", model_name)

        try:
            kwargs: Dict[str, Any] = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if tools is not None:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = tool_choice

            logger.debug("Chat completion request: model=%s, has_images=%s", model_name, has_images)
            return client.chat.completions.create(**kwargs)
        except Exception as e:
            logger.error("LLMService chat_completion failed: %s", e, exc_info=True)
            raise

    def chat_completion_text(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 768,
    ) -> str:
        try:
            response = self.chat_completion(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            logger.error("LLMService chat_completion_text failed: %s", e, exc_info=True)
            return "I'm having trouble reaching the AI model right now. Please try again."

    def generate_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        client = self.get_client()
        model_name = model or self.embedding_model
        try:
            response = client.embeddings.create(model=model_name, input=text)
            return response.data[0].embedding
        except Exception as e:
            logger.error("LLMService generate_embedding failed: %s", e, exc_info=True)
            raise

    def generate_embeddings_batch(
        self,
        texts: List[str],
        model: Optional[str] = None,
    ) -> List[List[float]]:
        client = self.get_client()
        model_name = model or self.embedding_model
        try:
            response = client.embeddings.create(model=model_name, input=texts)
            return [record.embedding for record in response.data]
        except Exception as e:
            logger.error("LLMService generate_embeddings_batch failed: %s", e, exc_info=True)
            raise


_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
