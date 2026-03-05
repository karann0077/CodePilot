import logging
import re

from app.config import Settings, get_settings
from app.services.cache import get_cache
from app.services.secrets_scanner import get_secrets_scanner

logger = logging.getLogger(__name__)


class LLMOrchestrator:
    """Orchestrates LLM calls via Ollama (local) or OpenRouter (cloud)."""

    def __init__(self, config: Settings) -> None:
        self._config = config

    async def generate(
        self,
        prompt: str,
        system: str = "",
        repo_id: str = "",
        use_cache: bool = True,
    ) -> str:
        """
        Generate a response for the given prompt.

        Tries Ollama first, falls back to OpenRouter.
        Applies secrets redaction before returning.
        """
        cache = get_cache()
        cache_key = cache.make_key(repo_id, (system + "|" + prompt))

        if use_cache:
            cached = cache.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit for key %s", cache_key)
                return cached

        result: str | None = await self._try_ollama(prompt, system)
        if result is None:
            result = await self._call_openrouter(prompt, system)

        scanner = get_secrets_scanner()
        result = scanner.redact(result)

        if use_cache:
            cache.set(cache_key, result)

        return result

    async def _try_ollama(self, prompt: str, system: str) -> str | None:
        """Attempt to call the local Ollama instance. Returns None on failure."""
        try:
            import httpx

            full_prompt = f"{system}\n\n{prompt}" if system else prompt
            url = f"{self._config.ollama_base_url}/api/generate"
            payload = {
                "model": self._config.ollama_model,
                "prompt": full_prompt,
                "stream": False,
            }
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("response", "")
        except Exception as exc:
            logger.debug("Ollama unavailable: %s", exc)
            return None

    async def _call_openrouter(self, prompt: str, system: str) -> str:
        """Call OpenRouter API. Raises on failure."""
        try:
            import httpx

            url = "https://openrouter.ai/api/v1/chat/completions"
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            headers = {
                "Authorization": f"Bearer {self._config.openrouter_api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self._config.openrouter_model,
                "messages": messages,
            }
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as exc:
            logger.error("OpenRouter call failed: %s", exc)
            return f"Error: LLM unavailable ({exc})"

    def assemble_prompt(
        self, chunks: list[dict], question: str, task: str = "query"
    ) -> tuple[str, str]:
        """
        Build system and user prompts from retrieved chunks and a question.

        Returns (system_prompt, user_prompt).
        """
        system = (
            "You are CodePilot, an AI code assistant. "
            "Answer questions about code accurately and concisely. "
            "Always cite file paths and line numbers."
        )

        snippets: list[str] = []
        for chunk in chunks:
            lang = chunk.get("language", "")
            file_path = chunk.get("file_path", "unknown")
            start_line = chunk.get("start_line", 0)
            end_line = chunk.get("end_line", 0)
            text = chunk.get("text", "")
            header = f"[File: {file_path} L{start_line}-{end_line}]"
            snippets.append(f"{header}\n```{lang}\n{text}\n```")

        context = "\n\n".join(snippets)
        user_prompt = f"Context:\n\n{context}\n\n---\n\n{question}"
        return system, user_prompt


_orchestrator_instance: LLMOrchestrator | None = None


def get_orchestrator() -> LLMOrchestrator:
    """Return the singleton LLMOrchestrator instance."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = LLMOrchestrator(config=get_settings())
    return _orchestrator_instance
