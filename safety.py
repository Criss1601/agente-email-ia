"""Reglas para NO responder: evita bucles de correo, spam y mensajes automáticos."""

from __future__ import annotations

import re
from email.message import Message
from email.utils import parseaddr

_NOREPLY = re.compile(
    r"(^|[._+-])(no-?reply|do-?not-?reply|donotreply|mailer-daemon|postmaster|"
    r"bounce[s]?|notifications?|newsletter|automated)([._+@-]|$)",
    re.IGNORECASE,
)


def extract_address(header_value: str) -> str:
    return parseaddr(header_value or "")[1].strip().lower()


def ignore_reason(msg: Message, own_address: str) -> str | None:
    """Devuelve el motivo para ignorar el correo, o None si se puede responder."""
    sender = extract_address(msg.get("From", ""))
    if not sender or "@" not in sender:
        return "remitente inválido"

    if sender == own_address.strip().lower():
        return "correo enviado por el propio agente"

    if _NOREPLY.search(sender):
        return "remitente no-reply / sistema"

    auto = (msg.get("Auto-Submitted") or "").strip().lower()
    if auto and auto != "no":
        return f"Auto-Submitted: {auto}"

    precedence = (msg.get("Precedence") or "").strip().lower()
    if precedence in {"bulk", "junk", "list", "auto_reply"}:
        return f"Precedence: {precedence}"

    if msg.get("List-Unsubscribe") or msg.get("List-Id"):
        return "lista de correo / newsletter"

    if msg.get("X-Auto-Response-Suppress"):
        return "X-Auto-Response-Suppress presente"

    ctype = (msg.get_content_type() or "").lower()
    if ctype == "multipart/report":
        return "reporte de entrega (rebote)"

    subject = (msg.get("Subject") or "").lower()
    if re.match(r"^\s*(auto(matic)?[ -]?(reply|response)|respuesta autom[aá]tica|out of office|fuera de oficina)", subject):
        return "respuesta automática detectada por asunto"

    return None
