"""Environment configuration for the Talentrupt Marketing Agent backend.

All secrets live in ``backend/.env`` (gitignored). Nothing here should be
committed with a real key. See ``.env.example`` for the template.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database -------------------------------------------------------
    # SQLite dev default; switch to postgresql+psycopg://... for production.
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'talentrupt.db').as_posix()}"

    # --- LLM provider ---------------------------------------------------
    # "openai" | "none". "none" => deterministic streamed fallback (no key needed).
    llm_provider: str = "none"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    # Web-search-enabled model for live hiring-signal discovery (Business Dev).
    openai_search_model: str = "gpt-4o-mini-search-preview"

    # --- Targeting ------------------------------------------------------
    # The whole app targets the US market by default. Prospect/company discovery defaults to
    # this location (and drops clearly non-US results) unless the user names another country.
    default_location: str = "United States"

    # --- Contact enrichment (optional; off by default) ------------------
    # When configured, Business Dev can fetch REAL, provider-VERIFIED decision-maker contacts
    # (name/email) on demand. Until a key is set this is a no-op and contacts stay role-only.
    # "none" | "apollo" | "hunter".
    enrichment_provider: str = "none"
    enrichment_api_key: str = ""
    enrichment_base_url: str = ""  # optional override; adapters default to the provider's API

    def enrichment_available(self) -> bool:
        return self.enrichment_provider.strip().lower() not in ("", "none") and bool(
            self.enrichment_api_key.strip()
        )

    # --- Brand knowledge (source library) ------------------------------
    knowledge_zip_path: str = r"C:\Users\Admin\Downloads\TR POSTS ZIP.zip"
    knowledge_use_vision: bool = True
    knowledge_max_images: int = 200  # cap vision calls; archive has ~80
    # Extra standalone PDFs to ingest into the brand library (e.g. the sales deck).
    knowledge_extra_pdfs: str = r"C:\Users\Admin\Downloads\TalentRupt RPO Salesdeck.pdf"

    @property
    def knowledge_extra_pdf_list(self) -> list[str]:
        return [p.strip() for p in self.knowledge_extra_pdfs.split(";") if p.strip()]

    # --- Image provider -------------------------------------------------
    # "openai" -> gpt-image-1 (rich, illustrative); "compositor" -> deterministic
    # brand template; "none" -> compositor. The compositor is always the fallback.
    image_provider: str = "none"
    openai_image_model: str = "gpt-image-1"
    openai_image_quality: str = "high"  # low | medium | high | auto
    openai_image_size: str = "1024x1024"

    # --- Auth (dev) -----------------------------------------------------
    admin_username: str = "Admin@talentrupt.com"
    admin_password: str = "Admin123"
    admin_token: str = "dev-talentrupt-admin-token"

    # --- Brand logo -----------------------------------------------------
    # Path to the REAL Talentrupt logo PNG (navy "TR" in a coral-red square). When set and the file
    # exists, it is used verbatim for every generated asset (image/deck/PDF). When empty, a close
    # synthesized fallback is rendered. Drop the official logo here to make every generation exact.
    brand_logo_path: str = ""

    # --- Storage / CORS -------------------------------------------------
    storage_dir: str = str(PROJECT_DIR / "storage")
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @model_validator(mode="after")
    def _coerce_empty_to_defaults(self) -> "Settings":
        """Empty values in .env should fall back to safe defaults, not break boot.

        (e.g. an empty ``DATABASE_URL=`` line must not produce an unparsable URL.)
        """
        if not self.database_url.strip():
            self.database_url = f"sqlite:///{(BACKEND_DIR / 'talentrupt.db').as_posix()}"
        if not self.llm_provider.strip():
            self.llm_provider = "none"
        if not self.image_provider.strip():
            self.image_provider = "none"
        if not self.enrichment_provider.strip():
            self.enrichment_provider = "none"
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def storage_path(self) -> Path:
        p = Path(self.storage_dir)
        p.mkdir(parents=True, exist_ok=True)
        for sub in ("images", "decks", "pdfs"):
            (p / sub).mkdir(parents=True, exist_ok=True)
        return p

    @property
    def uploads_path(self) -> Path:
        p = Path(self.storage_dir) / "uploads"
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
