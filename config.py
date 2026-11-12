"""Configuración cargada desde variables de entorno (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Falta la variable de entorno obligatoria: {name}")
    return value


@dataclass(frozen=True)
class Config:
    # IA
    anthropic_api_key: str
    model: str
    max_tokens: int

    # Correo
    email_address: str
    email_password: str
    imap_host: str
    imap_port: int
    smtp_host: str
    smtp_port: int
    smtp_security: str  # "ssl" | "starttls"

    # Negocio
    company_name: str
    agent_name: str
    signature: str
    knowledge_file: Path
    default_language: str

    # Operación
    poll_interval: int
    db_path: Path
    heartbeat_file: Path
    log_level: str
    dry_run: bool

    # Límites anti-abuso / anti-bucle
    max_replies_per_sender_per_day: int
    max_replies_per_day: int
    max_body_chars: int
    escalation_email: str  # opcional: copia informativa cuando la IA no está segura

    @classmethod
    def from_env(cls, env_file: str | None = None) -> "Config":
        load_dotenv(env_file)
        return cls(
            anthropic_api_key=_require("ANTHROPIC_API_KEY"),
            model=os.environ.get("AI_MODEL", "claude-sonnet-5-5"),
            max_tokens=int(os.environ.get("AI_MAX_TOKENS", "1200")),
            email_address=_require("EMAIL_ADDRESS"),
            email_password=_require("EMAIL_PASSWORD"),
            imap_host=_require("IMAP_HOST"),
            imap_port=int(os.environ.get("IMAP_PORT", "993")),
            smtp_host=_require("SMTP_HOST"),
            smtp_port=int(os.environ.get("SMTP_PORT", "465")),
            smtp_security=os.environ.get("SMTP_SECURITY", "ssl").lower(),
            company_name=os.environ.get("COMPANY_NAME", "Mi Empresa"),
            agent_name=os.environ.get("AGENT_NAME", "Asistente Virtual"),
            signature=os.environ.get(
                "EMAIL_SIGNATURE",
                "Equipo de Atención al Cliente",
            ).replace("\\n", "\n"),
            knowledge_file=Path(
                os.environ.get("KNOWLEDGE_FILE", "config/knowledge_base.md")
            ),
            default_language=os.environ.get("DEFAULT_LANGUAGE", "es"),
            poll_interval=int(os.environ.get("POLL_INTERVAL_SECONDS", "30")),
            db_path=Path(os.environ.get("DB_PATH", "data/agente.db")),
            heartbeat_file=Path(
                os.environ.get("HEARTBEAT_FILE", "data/heartbeat")
            ),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            dry_run=_bool(os.environ.get("DRY_RUN"), False),
            max_replies_per_sender_per_day=int(
                os.environ.get("MAX_REPLIES_PER_SENDER_PER_DAY", "5")
            ),
            max_replies_per_day=int(os.environ.get("MAX_REPLIES_PER_DAY", "500")),
            max_body_chars=int(os.environ.get("MAX_BODY_CHARS", "8000")),
            escalation_email=os.environ.get("ESCALATION_EMAIL", "").strip(),
        )
