import logging

import httpx

from app.config import Settings, get_settings
from app.services.cache import get_cache
from app.services.secrets_scanner import get_secrets_scanner

logger = logging.getLogger(__name__)


class LLMOrchestrator:
    """Orchestrates LLM calls via Ollama/Groq/OpenRouter or Gemini-only mode."""

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

        In `gemini_only` mode, calls Gemini directly.
        In `groq_only` mode, calls Groq directly.
        Otherwise tries Ollama first, then Groq, then OpenRouter fallback.
        Applies secrets redaction before returning.
        """
        cache = get_cache()
        mode = self._config.llm_mode.strip().lower()
        provider_signature = (
            f"mode={mode}|gemini={self._config.gemini_model}"
            f"|groq={self._config.groq_model}|openrouter={self._config.openrouter_model}"
            f"|ollama={self._config.ollama_model}"
        )
        cache_key = cache.make_key(repo_id, provider_signature + "|" + system + "|" + prompt)

        if use_cache:
            cached = cache.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit for key %s", cache_key)
                return cached

        if mode == "gemini_only":
            result = await self._call_gemini(prompt, system)
        elif mode == "groq_only":
            result = await self._call_groq(prompt, system)
        else:
            result = await self._try_ollama(prompt, system)
            if result is None:
                result = await self._call_groq(prompt, system)
            if result.startswith("Error: LLM unavailable"):
                result = await self._call_openrouter(prompt, system)

        scanner = get_secrets_scanner()
        result = scanner.redact(result)

        if use_cache and not result.startswith("Error: LLM unavailable"):
            cache.set(cache_key, result)

        return result

    async def _try_ollama(self, prompt: str, system: str) -> str | None:
        """Attempt to call the local Ollama instance. Returns None on failure."""
        try:
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

    async def _call_gemini(self, prompt: str, system: str) -> str:
        """Call Gemini API directly with model fallback on 404."""
        try:
            if not self._config.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is not configured")

            full_prompt = f"{system}\n\n{prompt}" if system else prompt
            configured = self._config.gemini_model.strip()
            candidates = [
                configured,
                "gemini-1.5-flash-latest",
                "gemini-2.0-flash",
            ]
            model_candidates = list(dict.fromkeys([m for m in candidates if m]))

            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": full_prompt},
                        ]
                    }
                ]
            }

            async with httpx.AsyncClient(timeout=90.0) as client:
                last_exc: Exception | None = None
                for model in model_candidates:
                    url = (
                        "https://generativelanguage.googleapis.com/v1beta/models/"
                        f"{model}:generateContent"
                    )
                    try:
                        response = await client.post(
                            url,
                            params={"key": self._config.gemini_api_key},
                            json=payload,
                        )
                        response.raise_for_status()
                        data = response.json()
                        response_candidates = data.get("candidates", [])
                        if not response_candidates:
                            return ""
                        parts = response_candidates[0].get("content", {}).get("parts", [])
                        return "".join(part.get("text", "") for part in parts)
                    except httpx.HTTPStatusError as exc:
                        last_exc = exc
                        if exc.response.status_code == 404:
                            logger.warning("Gemini model not found: %s", model)
                            continue
                        raise
                if last_exc is not None:
                    raise last_exc
                raise ValueError("No Gemini model candidates configured")
        except Exception as exc:
            logger.error("Gemini call failed: %s", exc)
            return f"Error: LLM unavailable ({exc})"

    async def _call_groq(self, prompt: str, system: str) -> str:
        """Call Groq API with model fallback."""
        try:
            if not self._config.groq_api_key:
                raise ValueError("GROQ_API_KEY is not configured")

            configured_model = self._config.groq_model.strip()
            model_candidates = [
                configured_model,
                "llama-3.1-8b-instant",
                "gemma2-9b-it",
                "llama-3.3-70b-versatile",
            ]
            model_candidates = list(dict.fromkeys([m for m in model_candidates if m]))

            url = "https://api.groq.com/openai/v1/chat/completions"
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            headers = {
                "Authorization": f"Bearer {self._config.groq_api_key}",
                "Content-Type": "application/json",
            }

            async with httpx.AsyncClient(timeout=90.0) as client:
                last_exc: Exception | None = None
                for model in model_candidates:
                    payload = {"model": model, "messages": messages}
                    try:
                        response = await client.post(url, json=payload, headers=headers)
                        response.raise_for_status()
                        data = response.json()
                        return data["choices"][0]["message"]["content"]
                    except httpx.HTTPStatusError as exc:
                        body = exc.response.text[:300]
                        last_exc = RuntimeError(
                            f"Groq error for model '{model}' (status {exc.response.status_code}): {body}"
                        )
                        if exc.response.status_code in {400, 404}:
                            logger.warning("Groq model unavailable, retrying next candidate: %s", model)
                            continue
                        raise last_exc

                if last_exc is not None:
                    raise last_exc
                raise ValueError("No Groq model candidates configured")
        except Exception as exc:
            logger.error("Groq call failed: %s", exc)
            return f"Error: LLM unavailable ({exc})"

    async def _call_openrouter(self, prompt: str, system: str) -> str:
        """Call OpenRouter API with endpoint discovery and model fallback."""
        try:
            if not self._config.openrouter_api_key:
                raise ValueError("OPENROUTER_API_KEY is not configured")

            configured_model = self._config.openrouter_model.strip()
            model_candidates = [
                configured_model,
                "meta-llama/llama-3.1-8b-instruct:free",
                "mistralai/mistral-7b-instruct:free",
                "deepseek/deepseek-r1-0528:free",
            ]
            model_candidates = list(dict.fromkeys([m for m in model_candidates if m]))

            if not self._config.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is not configured")

            full_prompt = f"{system}\n\n{prompt}" if system else prompt
            model = self._config.gemini_model
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent"
            )
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": full_prompt},
                        ]
                    }
                ]
            }

            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(
                    url,
                    params={"key": self._config.gemini_api_key},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    return ""
                parts = candidates[0].get("content", {}).get("parts", [])
                return "".join(part.get("text", "") for part in parts)
        except Exception as exc:
            logger.error("Gemini call failed: %s", exc)
            return f"Error: LLM unavailable ({exc})"

    async def _call_openrouter(self, prompt: str, system: str) -> str:
        """Call OpenRouter API with model fallback and detailed error surfacing."""
        try:
            if not self._config.openrouter_api_key:
                raise ValueError("OPENROUTER_API_KEY is not configured")

            configured_model = self._config.openrouter_model.strip()
            model_candidates = [
                configured_model,
                "meta-llama/llama-3.1-8b-instruct:free",
                "mistralai/mistral-7b-instruct:free",
                "google/gemma-2-9b-it:free",
            ]
            model_candidates = list(dict.fromkeys([m for m in model_candidates if m]))

            url = "https://openrouter.ai/api/v1/chat/completions"
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            headers = {
                "Authorization": f"Bearer {self._config.openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://codepilot.local",
                "X-Title": "CodePilot",
            }

            async with httpx.AsyncClient(timeout=90.0) as client:
                last_exc: Exception | None = None

                async def try_models(candidates: list[str]) -> str | None:
                    nonlocal last_exc
                    for model in candidates:
                        payload = {"model": model, "messages": messages}
                        try:
                            response = await client.post(url, json=payload, headers=headers)
                            response.raise_for_status()
                            data = response.json()
                            return data["choices"][0]["message"]["content"]
                        except httpx.HTTPStatusError as exc:
                            body = exc.response.text[:300]
                            last_exc = RuntimeError(
                                f"OpenRouter error for model '{model}' (status {exc.response.status_code}): {body}"
                            )
                            if exc.response.status_code == 404:
                                logger.warning("OpenRouter model unavailable, retrying next candidate: %s", model)
                                continue
                            raise last_exc
                    return None

                output = await try_models(model_candidates)
                if output is not None:
                    return output

                # If configured/static candidates all failed with 404, discover available free models and retry.
                try:
                    models_resp = await client.get("https://openrouter.ai/api/v1/models", headers=headers)
                    models_resp.raise_for_status()
                    model_data = models_resp.json().get("data", [])
                    discovered_free = [
                        item.get("id", "")
                        for item in model_data
                        if isinstance(item, dict) and str(item.get("id", "")).endswith(":free")
                    ]
                    discovered_free = list(dict.fromkeys([m for m in discovered_free if m]))[:12]
                    if discovered_free:
                        logger.info("Retrying OpenRouter with discovered free models (%d candidates)", len(discovered_free))
                        output = await try_models(discovered_free)
                        if output is not None:
                            return output
                except Exception as exc:
                    logger.warning("OpenRouter model discovery failed: %s", exc)

                if last_exc is not None:
                    raise last_exc
                raise ValueError("No OpenRouter model candidates configured")
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
