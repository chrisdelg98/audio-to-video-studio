"""Local AI backend client for Prompt Lab."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import error as url_error
from urllib import request as url_request


@dataclass
class PromptBackendConfig:
    base_url: str
    quality_model: str
    fast_model: str
    timeout_seconds: int = 120


class PromptLabBackendError(RuntimeError):
    """Raised when the local AI backend cannot generate a response."""


class PromptLabBackend:
    """Minimal local-LLM client with model routing per mode."""

    def generate(
        self,
        *,
        prompt: str,
        skill_instructions: str,
        mode: str,
        config: PromptBackendConfig,
    ) -> str:
        model = config.quality_model if mode == "Calidad alta" else config.fast_model
        if not model.strip():
            raise PromptLabBackendError("No hay modelo configurado para este modo.")

        base_url = config.base_url.rstrip("/")
        if not base_url:
            raise PromptLabBackendError("URL del backend local vacia.")

        last_error = ""

        try:
            return self._call_ollama_generate(
                base_url=base_url,
                model=model,
                prompt=prompt,
                skill_instructions=skill_instructions,
                timeout_seconds=config.timeout_seconds,
            )
        except PromptLabBackendError as exc:
            last_error = str(exc)

        try:
            return self._call_openai_compatible_chat(
                base_url=base_url,
                model=model,
                prompt=prompt,
                skill_instructions=skill_instructions,
                timeout_seconds=config.timeout_seconds,
            )
        except PromptLabBackendError as exc:
            last_error = str(exc)

        raise PromptLabBackendError(
            "No se pudo generar respuesta con backend local. "
            f"Detalle: {last_error or 'sin detalle'}"
        )

    def _call_ollama_generate(
        self,
        *,
        base_url: str,
        model: str,
        prompt: str,
        skill_instructions: str,
        timeout_seconds: int,
    ) -> str:
        payload = {
            "model": model,
            "prompt": prompt,
            "system": skill_instructions or "",
            "stream": False,
        }
        raw = self._post_json(
            url=f"{base_url}/api/generate",
            payload=payload,
            timeout_seconds=timeout_seconds,
        )
        response = str(raw.get("response", "")).strip()
        if response:
            return response
        raise PromptLabBackendError("Respuesta vacia desde /api/generate.")

    def _call_openai_compatible_chat(
        self,
        *,
        base_url: str,
        model: str,
        prompt: str,
        skill_instructions: str,
        timeout_seconds: int,
    ) -> str:
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": skill_instructions or "Responde de forma util y accionable.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.6,
        }
        raw = self._post_json(
            url=f"{base_url}/v1/chat/completions",
            payload=payload,
            timeout_seconds=timeout_seconds,
        )
        choices = raw.get("choices", [])
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                msg = first.get("message", {})
                if isinstance(msg, dict):
                    content = str(msg.get("content", "")).strip()
                    if content:
                        return content
        raise PromptLabBackendError("Respuesta vacia desde /v1/chat/completions.")

    def _post_json(self, *, url: str, payload: dict, timeout_seconds: int) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = url_request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with url_request.urlopen(req, timeout=max(10, int(timeout_seconds))) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except url_error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = str(exc)
            raise PromptLabBackendError(f"HTTP {exc.code} en {url}: {detail}") from exc
        except Exception as exc:
            raise PromptLabBackendError(f"No se pudo conectar a {url}: {exc}") from exc

        try:
            parsed = json.loads(body)
        except Exception as exc:
            raise PromptLabBackendError(f"Respuesta JSON invalida de {url}: {body[:200]}") from exc

        if not isinstance(parsed, dict):
            raise PromptLabBackendError(f"Respuesta no compatible de {url}.")
        return parsed
