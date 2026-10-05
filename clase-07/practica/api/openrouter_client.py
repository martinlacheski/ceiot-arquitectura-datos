"""Cliente mínimo y acotado para OpenRouter, sin reintentos pagos implícitos."""

from __future__ import annotations

import os
from typing import Any

import httpx  # type: ignore[import-not-found]

from shared.settings import env_int  # type: ignore[import-not-found]

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"
# Tope global de tokens de salida por llamada. Cada flujo pide su propio valor
# (p. ej. 180 o 260 en workflows.py); `chat` aplica el menor de los dos, así que
# bajar este tope acorta todas las respuestas sin romper ningún flujo.
MAX_COMPLETION_TOKENS = env_int("OPENROUTER_MAX_COMPLETION_TOKENS", 300, minimum=1, maximum=4096)


class MissingOpenRouterKey(RuntimeError):
    """La aplicación puede arrancar aunque no haya una clave configurada."""


class OpenRouterError(RuntimeError):
    """Error seguro para mostrar sin filtrar cabeceras ni cuerpos remotos."""


class OpenRouterClient:
    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY", "")
        self.model = model or os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)
        if not self._api_key.strip():
            raise MissingOpenRouterKey(
                "Falta OPENROUTER_API_KEY; configurala para usar los modos de IA."
            )
        if not self.model.strip():
            raise RuntimeError("OPENROUTER_MODEL no puede estar vacío")

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_completion_tokens: int = MAX_COMPLETION_TOKENS,
    ) -> str:
        if max_completion_tokens < 1:
            raise ValueError("max_completion_tokens debe ser al menos 1")
        max_completion_tokens = min(max_completion_tokens, MAX_COMPLETION_TOKENS)
        try:
            with httpx.Client(timeout=httpx.Timeout(12.0, connect=4.0)) as client:
                response = client.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "max_completion_tokens": max_completion_tokens,
                        "temperature": 0,
                    },
                )
            response.raise_for_status()
            payload: Any = response.json()
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise (ValueError("respuesta vacía"))
            return content.strip()
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            # No incluir respuesta, request ni cabeceras: podrían contener datos sensibles.
            raise OpenRouterError(
                "OpenRouter no pudo completar la solicitud; revisá modelo, saldo y conectividad."
            ) from error
