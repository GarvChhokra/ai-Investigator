from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PKG_ROOT = Path(__file__).resolve().parent.parent


def _default_csv() -> str:
    return str(_PKG_ROOT.parent / "investigator-be" / "data" / "sample_cases_synthetic.csv")


class AiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_PKG_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- model access -----------------------------------------------------
    gemini_api_key: str | None = None
    ai_model: str = "gemini-3.1-flash-lite"
    llm_temperature: float = 0.1

    # --- reasoning behaviour --------------------------------------------
    max_assessment_attempts: int = 2

    # --- data: path to the referral queue CSV --------------------------
    cases_csv: str = _default_csv()
