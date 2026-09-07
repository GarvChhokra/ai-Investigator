"""Gemini clients - the only place the LLM SDK is imported.

One client per use so each owns its own concerns (structured output for assessment, plain
+ streaming text for questions) and tests can substitute a fake per graph.
"""

from __future__ import annotations

from collections.abc import Iterator

from investigator_ai.schemas import AssessmentLLM

_DEFAULT_TEMPERATURE = 0.1
_MAX_RETRIES = 2

class LlmUnavailable(RuntimeError):
    """Raised when a call is requested but no API key / SDK is available."""


class _BaseGeminiClient:
    def __init__(self, model: str, api_key: str | None, temperature: float = _DEFAULT_TEMPERATURE):
        self._model_id = model
        self._api_key = api_key
        self._temperature = temperature
        self._client = None

    @property
    def model_id(self) -> str:
        return self._model_id

    def _chat(self):
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise LlmUnavailable("No GEMINI_API_KEY configured.")
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:  # pragma: no cover
            raise LlmUnavailable(f"langchain-google-genai not importable: {exc}") from exc
        self._client = ChatGoogleGenerativeAI(
            model=self._model_id,
            temperature=self._temperature,
            google_api_key=self._api_key,
            max_retries=_MAX_RETRIES,
        )
        return self._client


class AssessmentLlmClient(_BaseGeminiClient):
    def assess(self, system_prompt: str, user_prompt: str) -> AssessmentLLM:
        """One schema-constrained call. Raises LlmUnavailable or any model/parse error."""
        # json_mode keeps this a plain constrained-decoding call (no function-calling / AFC).
        model = self._chat().with_structured_output(AssessmentLLM, method="json_mode")
        raw = model.invoke([("system", system_prompt), ("human", user_prompt)])
        return raw if isinstance(raw, AssessmentLLM) else AssessmentLLM.model_validate(raw)


def _text_of(message) -> str:
    """Flatten a LangChain message's content to plain text.

    Newer Gemini models return a list of typed content blocks
    (``[{"type": "text", "text": ...}, ...]``) rather than a bare string.
    """
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type", "text") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return str(content)


class QuestionLlmClient(_BaseGeminiClient):
    def answer(self, system_prompt: str, user_prompt: str) -> str:
        resp = self._chat().invoke([("system", system_prompt), ("human", user_prompt)])
        return _text_of(resp)

    def stream(self, system_prompt: str, user_prompt: str) -> Iterator[str]:
        for chunk in self._chat().stream([("system", system_prompt), ("human", user_prompt)]):
            piece = _text_of(chunk)
            if piece:
                yield piece
