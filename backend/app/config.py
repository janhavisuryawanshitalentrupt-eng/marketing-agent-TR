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
    # gpt-image-2 is OpenAI's latest image model (released 2026; verified live — generates b64 like
    # gpt-image-1, accepts quality=high). Requires an OPENAI_API_KEY with gpt-image-2 access. Switchable
    # via OPENAI_IMAGE_MODEL; llm.py falls back to gpt-image-1 automatically if the configured model is
    # ever unavailable (e.g. the key lacks access), so generation can never break.
    openai_image_model: str = "gpt-image-2"
    openai_image_quality: str = "high"  # low | medium | high | auto
    openai_image_size: str = "1024x1024"

    # --- Employee photo cut-out (background removal) --------------------
    # For "floating on the scene" employee posts we can remove the photo background via a hosted API
    # (keeps the 2GB droplet free of rembg/onnxruntime). "none" -> no API; the composer falls back to the
    # designed framed card. "removebg" -> api.remove.bg; "photoroom" -> Photoroom. Set the key to enable.
    # The API only strips the BACKGROUND — the real face pixels are never altered.
    bg_removal_provider: str = "none"      # none | removebg | photoroom
    bg_removal_api_key: str = ""

    # --- Employee AI-portrait FACE-SWAP (optional) ---------------------
    # To make a fully AI portrait (blazer, polished scene) that keeps the person's EXACT real face, the app
    # generates an AI portrait with gpt-image, then SWAPS the person's real face onto it via a hosted
    # face-swap API (keeps heavy insightface/onnxruntime OFF the 2GB droplet). "none" -> no face-swap; the
    # composer keeps the plain real photo (exact face, no AI clothes). "replicate" -> a Replicate face-swap
    # model. Set the key to enable. The swap keeps the real FACE — only the body/clothes/background are AI.
    faceswap_provider: str = "none"        # none | replicate
    faceswap_api_key: str = ""
    faceswap_model: str = "cdingram/face-swap"   # Replicate "owner/name" (its latest version is used)
    faceswap_target_key: str = "input_image"     # model input for the AI portrait (WHERE the face goes)
    faceswap_source_key: str = "swap_image"      # model input for the REAL photo (the face to apply)

    def faceswap_available(self) -> bool:
        return self.faceswap_provider.strip().lower() not in ("", "none") and bool(
            self.faceswap_api_key.strip()
        )

    # --- Auth (dev) -----------------------------------------------------
    admin_username: str = "Admin@talentrupt.com"
    admin_password: str = "Admin123"
    admin_token: str = "dev-talentrupt-admin-token"
    # A second, NON-admin team member. This role does NOT see the Tasks or Analytics sections (the
    # nav is hidden AND those APIs are admin-only). Override via env (MEMBER_PASSWORD) in production.
    member_username: str = "nishant@talentrupt.com"
    member_password: str = "NT@tr@2026"
    member_token: str = "dev-talentrupt-member-token"
    # Additional (non-admin) member logins beyond the primary one, as "email:password,email2:pw2".
    # Override via env EXTRA_MEMBER_LOGINS. Each extra member gets a stable, unforgeable session token
    # derived (HMAC) from member_token — so it survives restarts and can't be guessed. (Internal-tool
    # pattern: credentials live in config/.env; move to per-user hashing when hardening.)
    extra_member_logins: str = "janhavisuryawanshi.talentrupt@gmail.com:janhavi123"

    def member_accounts(self) -> list[tuple[str, str, str]]:
        """(username, password, token) for every member login — the primary member plus any extras."""
        import hashlib
        import hmac

        out: list[tuple[str, str, str]] = [
            (self.member_username.strip(), self.member_password, self.member_token)
        ]
        for pair in (self.extra_member_logins or "").split(","):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            user, pw = pair.split(":", 1)
            user = user.strip()
            if not user:
                continue
            token = "m-" + hmac.new(
                self.member_token.encode(), user.lower().encode(), hashlib.sha256
            ).hexdigest()[:40]
            out.append((user, pw, token))
        return out

    # --- Email / password reset (optional) ------------------------------
    # SMTP is used to deliver the 'forgot password' reset code to the admin email. Until host+from are
    # set, the reset flow still works but the code is written to the server log instead of emailed.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""        # the From address (e.g. "Talentrupt AI <noreply@talentrupt.com>")
    smtp_starttls: bool = True
    # Dev-only convenience: when email is NOT configured, return the reset code in the API response so
    # the flow is testable. MUST stay False in any shared/production environment.
    auth_reset_dev_return_code: bool = False

    def email_available(self) -> bool:
        return bool(self.smtp_host.strip() and self.smtp_from.strip())

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
        if not self.faceswap_provider.strip():
            self.faceswap_provider = "none"
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
