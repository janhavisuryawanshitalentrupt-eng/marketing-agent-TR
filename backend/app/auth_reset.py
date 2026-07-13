"""Password verification + 'forgot password' reset flow.

The app ships a single admin account whose default password lives in config. To support a working
reset, the *current* password is stored as a salted PBKDF2 hash in the AppSetting key-value table once
the user resets it; until then the config password applies. Reset codes are 6 digits, hashed, single-
use, and expire in 15 minutes. Email delivery is via SMTP (config-gated) — until SMTP is configured the
code is logged server-side (and optionally returned in dev mode).

No new dependencies: hashlib/secrets/smtplib are stdlib.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from sqlalchemy.orm import Session

from .config import settings
from .models import AppSetting

log = logging.getLogger("talentrupt")

_PW_KEY = "admin_password_hash"
_RESET_KEY = "pwreset"
_CODE_TTL_MIN = 15
_MAX_ATTEMPTS = 5  # wrong guesses before the code is burned (brute-force guard: 6-digit space)
_ITER = 200_000


# --- key-value helpers ----------------------------------------------------
def _get(db: Session, key: str) -> str | None:
    row = db.get(AppSetting, key)
    return row.value if row else None


def _set(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row:
        row.value = value
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(AppSetting(key=key, value=value))
    db.commit()


def _del(db: Session, key: str) -> None:
    row = db.get(AppSetting, key)
    if row:
        db.delete(row)
        db.commit()


def _hash(secret: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", secret.encode(), bytes.fromhex(salt), _ITER).hex()


# --- password -------------------------------------------------------------
def set_password(db: Session, password: str) -> None:
    salt = secrets.token_hex(16)
    _set(db, _PW_KEY, json.dumps({"salt": salt, "hash": _hash(password, salt)}))


def verify_password(db: Session, password: str) -> bool:
    """True if the password matches the DB override (if a reset was done) else the config default."""
    raw = _get(db, _PW_KEY)
    if raw:
        try:
            d = json.loads(raw)
            return hmac.compare_digest(_hash(password, d["salt"]), d["hash"])
        except Exception:
            return False
    return hmac.compare_digest(password, settings.admin_password)


# --- reset code -----------------------------------------------------------
def create_reset_code(db: Session) -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    salt = secrets.token_hex(8)
    exp = (datetime.now(timezone.utc) + timedelta(minutes=_CODE_TTL_MIN)).isoformat()
    _set(db, _RESET_KEY, json.dumps({"salt": salt, "hash": _hash(code, salt), "exp": exp, "attempts": 0}))
    return code


def verify_reset_code(db: Session, code: str) -> bool:
    raw = _get(db, _RESET_KEY)
    if not raw:
        return False
    try:
        d = json.loads(raw)
        if datetime.fromisoformat(d["exp"]) < datetime.now(timezone.utc):
            _del(db, _RESET_KEY)
            return False
        if hmac.compare_digest(_hash(str(code).strip(), d["salt"]), d["hash"]):
            return True
        # Wrong code — count the attempt and burn the code after too many tries, so a 6-digit code
        # can't be brute-forced (at most _MAX_ATTEMPTS guesses per issued code).
        d["attempts"] = int(d.get("attempts", 0)) + 1
        if d["attempts"] >= _MAX_ATTEMPTS:
            _del(db, _RESET_KEY)
        else:
            _set(db, _RESET_KEY, json.dumps(d))
        return False
    except Exception:
        return False


def clear_reset_code(db: Session) -> None:
    _del(db, _RESET_KEY)


# --- email ----------------------------------------------------------------
def email_available() -> bool:
    return settings.email_available()


def send_reset_email(to: str, code: str) -> bool:
    """Deliver the reset code via SMTP. Returns False (no raise) if email isn't configured."""
    if not email_available():
        return False
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = "Your Talentrupt AI password reset code"
    msg.set_content(
        f"Your Talentrupt AI password reset code is: {code}\n\n"
        f"It expires in {_CODE_TTL_MIN} minutes. If you didn't request this, you can ignore this email."
    )
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
        if settings.smtp_starttls:
            s.starttls(context=ssl.create_default_context())
        if settings.smtp_user:
            s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(msg)
    return True
