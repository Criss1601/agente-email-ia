"""Acceso al correo: lectura por IMAP y envío por SMTP."""

from __future__ import annotations

import email
import imaplib
import logging
import re
import smtplib
import ssl
from dataclasses import dataclass
from email import policy
from email.message import EmailMessage, Message
from email.utils import formatdate, make_msgid, parseaddr

from .config import Config
from .safety import extract_address

log = logging.getLogger(__name__)


@dataclass
class IncomingEmail:
    uid: bytes
    message_id: str
    sender: str
    sender_name: str
    subject: str
    body: str
    references: str
    raw: Message


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", html)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    return re.sub(r"[ \t]+", " ", text)


def _strip_quoted(text: str) -> str:
    """Elimina el historial citado para no enviarlo a la IA ni gastar tokens."""
    lines: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith(">"):
            continue
        if re.match(r"^\s*(On .+ wrote:|El .+ escribi[oó]:)\s*$", line):
            break
        if re.match(r"^\s*-{2,}\s*(Original Message|Mensaje original)", line, re.I):
            break
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def extract_body(msg: Message, limit: int) -> str:
    text = ""
    if msg.is_multipart():
        plain, html = None, None
        for part in msg.walk():
            if part.get_content_disposition() == "attachment":
                continue
            ctype = part.get_content_type()
            if ctype == "text/plain" and plain is None:
                plain = part.get_content()
            elif ctype == "text/html" and html is None:
                html = part.get_content()
        text = plain if plain is not None else _html_to_text(html or "")
    else:
        payload = msg.get_content()
        text = _html_to_text(payload) if msg.get_content_type() == "text/html" else payload
    return _strip_quoted(text)[:limit]


class Mailbox:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._imap: imaplib.IMAP4_SSL | None = None

    # ---------- IMAP ----------
    def connect(self) -> None:
        self.close()
        imap = imaplib.IMAP4_SSL(
            self.cfg.imap_host, self.cfg.imap_port, timeout=60
        )
        imap.login(self.cfg.email_address, self.cfg.email_password)
        imap.select("INBOX")
        self._imap = imap
        log.info("Conectado a IMAP %s", self.cfg.imap_host)

    def close(self) -> None:
        if self._imap is not None:
            try:
                self._imap.logout()
            except Exception:  # noqa: BLE001
                pass
            self._imap = None

    def fetch_unseen(self) -> list[IncomingEmail]:
        if self._imap is None:
            self.connect()
        assert self._imap is not None
        self._imap.noop()
        status, data = self._imap.uid("SEARCH", None, "UNSEEN")
        if status != "OK":
            raise imaplib.IMAP4.error(f"SEARCH falló: {status}")
        result: list[IncomingEmail] = []
        for uid in data[0].split():
            status, msg_data = self._imap.uid("FETCH", uid, "(BODY.PEEK[])")
            if status != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                continue
            msg = email.message_from_bytes(msg_data[0][1], policy=policy.default)
            name, addr = parseaddr(msg.get("From", ""))
            mid = (msg.get("Message-ID") or "").strip() or f"uid-{uid.decode()}"
            result.append(
                IncomingEmail(
                    uid=uid,
                    message_id=mid,
                    sender=extract_address(msg.get("From", "")) or addr.lower(),
                    sender_name=name,
                    subject=str(msg.get("Subject") or "(sin asunto)"),
                    body=extract_body(msg, self.cfg.max_body_chars),
                    references=str(msg.get("References") or ""),
                    raw=msg,
                )
            )
        return result

    def mark_seen(self, uid: bytes) -> None:
        if self._imap is not None:
            self._imap.uid("STORE", uid, "+FLAGS", "(\\Seen)")

    # ---------- SMTP ----------
    def send_reply(
        self, incoming: IncomingEmail, body: str, cc: str | None = None
    ) -> None:
        subject = incoming.subject
        if not re.match(r"^\s*(re|rv):", subject, re.I):
            subject = f"Re: {subject}"

        msg = EmailMessage()
        msg["From"] = f"{self.cfg.agent_name} <{self.cfg.email_address}>"
        msg["To"] = (
            f"{incoming.sender_name} <{incoming.sender}>"
            if incoming.sender_name
            else incoming.sender
        )
        if cc:
            msg["Cc"] = cc
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=self.cfg.email_address.split("@")[-1])
        msg["In-Reply-To"] = incoming.message_id
        msg["References"] = (incoming.references + " " + incoming.message_id).strip()
        # Evita que otros autoresponders contesten a este mensaje (anti-bucle)
        msg["Auto-Submitted"] = "auto-replied"
        msg["X-Auto-Response-Suppress"] = "All"
        msg["Precedence"] = "auto_reply"
        msg.set_content(body)

        ctx = ssl.create_default_context()
        if self.cfg.smtp_security == "starttls":
            with smtplib.SMTP(self.cfg.smtp_host, self.cfg.smtp_port, timeout=60) as s:
                s.starttls(context=ctx)
                s.login(self.cfg.email_address, self.cfg.email_password)
                s.send_message(msg)
        else:
            with smtplib.SMTP_SSL(
                self.cfg.smtp_host, self.cfg.smtp_port, context=ctx, timeout=60
            ) as s:
                s.login(self.cfg.email_address, self.cfg.email_password)
                s.send_message(msg)
