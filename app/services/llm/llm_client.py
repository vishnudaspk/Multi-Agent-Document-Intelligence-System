"""
app/services/llm/llm_client.py

Unified LLM client — works with both Ollama and LMStudio
via the OpenAI-compatible API.

Usage:
    from app.services.llm.llm_client import LLMClient
    client = LLMClient()
    response = client.chat([{"role": "user", "content": "Hello"}])
    print(response)
"""
from __future__ import annotations

from typing import Iterator, List, Optional

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import logger


class LLMClient:
    """
    Thin wrapper around the OpenAI-compatible endpoint.
    Works unchanged with Ollama (/api/chat via OpenAI shim) and LMStudio (/v1).
    """

    def __init__(self):
        base_url = settings.llm_base_url
        # Ollama's OpenAI-compatible endpoint lives at /v1
        if "11434" in base_url and not base_url.endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"

        self._client = OpenAI(
            base_url=base_url,
            api_key=settings.llm_api_key,
        )
        self.model = settings.llm_model
        logger.info("llm_client.ready", base_url=base_url, model=self.model)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def chat(
        self,
        messages: List[dict],
        temperature: float = 0.1,
        max_tokens: int = 2048,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Send a chat completion request.
        Returns the assistant's reply as a plain string.
        """
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages

        logger.debug("llm.chat.request", model=self.model, msg_count=len(messages))

        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        reply = response.choices[0].message.content or ""
        logger.debug("llm.chat.response", tokens=response.usage.total_tokens if response.usage else "?")
        return reply

    def stream(
        self,
        messages: List[dict],
        temperature: float = 0.1,
        max_tokens: int = 2048,
        system_prompt: Optional[str] = None,
    ) -> Iterator[str]:
        """
        Streaming chat — yields text deltas as they arrive.
        Use with FastAPI StreamingResponse.
        """
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages

        stream = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


# ── Module-level singleton ────────────────────────────────────────────────────
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
