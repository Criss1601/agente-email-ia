"""Bucle principal del agente: corre indefinidamente y se recupera solo de fallos."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from pathlib import Path

from .ai import Responder
from .config import Config
from .mailbox import IncomingEmail, Mailbox
from .safety import ignore_reason
from .store import Store

log = logging.getLogger("agente_email")

_running = True
MAX_ATTEMPTS = 3


def _stop(signum, _frame) -> None:  # noqa: ANN001
    global _running
    log.info("Señal %s recibida: apagando de forma ordenada…", signum)
    _running = False


def _heartbeat(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(int(time.time())))
    except OSError:
        pass


def handle_email(
    cfg: Config, mailbox: Mailbox, responder: Responder, store: Store, mail: IncomingEmail
) -> None:
    if store.seen(mail.message_id):
        mailbox.mark_seen(mail.uid)
        return

    reason = ignore_reason(mail.raw, cfg.email_address)
    if reason:
        log.info("Ignorado (%s): %s", reason, mail.sender)
        store.mark(mail.message_id, mail.sender, mail.subject, "ignored", reason)
        mailbox.mark_seen(mail.uid)
        return

    if (
        store.replies_since(mail.sender) >= cfg.max_replies_per_sender_per_day
        or store.total_replies_since() >= cfg.max_replies_per_day
    ):
        log.warning("Límite diario alcanzado, no se responde a %s", mail.sender)
        store.mark(mail.message_id, mail.sender, mail.subject, "rate_limited")
        mailbox.mark_seen(mail.uid)
        return

    if not mail.body.strip():
        store.mark(mail.message_id, mail.sender, mail.subject, "ignored", "cuerpo vacío")
        mailbox.mark_seen(mail.uid)
        return

    ai_reply = responder.reply_to(mail.sender_name, mail.subject, mail.body)
    cc = cfg.escalation_email if (ai_reply.confidence == "low" and cfg.escalation_email) else None

    if cfg.dry_run:
        log.info("[DRY_RUN] Respondería a %s (%s):\n%s", mail.sender, ai_reply.confidence, ai_reply.text)
        store.mark(mail.message_id, mail.sender, mail.subject, "dry_run", ai_reply.reason)
        return

    mailbox.send_reply(mail, ai_reply.text, cc=cc)
    store.mark(mail.message_id, mail.sender, mail.subject, "replied", f"{ai_reply.confidence}: {ai_reply.reason}")
    mailbox.mark_seen(mail.uid)
    log.info("Respondido a %s (confianza=%s)", mail.sender, ai_reply.confidence)


def run(cfg: Config, once: bool = False) -> int:
    knowledge = ""
    if cfg.knowledge_file.exists():
        knowledge = cfg.knowledge_file.read_text(encoding="utf-8")
    else:
        log.warning("No existe la base de conocimiento: %s", cfg.knowledge_file)

    store = Store(cfg.db_path)
    responder = Responder(cfg, knowledge)
    mailbox = Mailbox(cfg)
    backoff = 5
    failures: dict[str, int] = {}

    log.info("Agente iniciado (modelo=%s, dry_run=%s)", cfg.model, cfg.dry_run)
    while _running:
        try:
            for mail in mailbox.fetch_unseen():
                if not _running:
                    break
                try:
                    handle_email(cfg, mailbox, responder, store, mail)
                except Exception as exc:  # noqa: BLE001
                    # Un correo problemático no debe detener al agente.
                    log.exception("Error procesando %s", mail.message_id)
                    failures[mail.message_id] = failures.get(mail.message_id, 0) + 1
                    if failures[mail.message_id] >= MAX_ATTEMPTS:
                        # Tras varios fallos se descarta para no reintentar eternamente.
                        store.mark(mail.message_id, mail.sender, mail.subject, "gave_up", str(exc))
                        mailbox.mark_seen(mail.uid)
                        failures.pop(mail.message_id, None)
                    else:
                        store.mark(mail.message_id, mail.sender, mail.subject, "failed", str(exc))
            backoff = 5
            _heartbeat(cfg.heartbeat_file)
            if once:
                break
            for _ in range(cfg.poll_interval):
                if not _running:
                    break
                time.sleep(1)
        except Exception:  # noqa: BLE001
            log.exception("Error de conexión; reintentando en %ss", backoff)
            mailbox.close()
            if once:
                return 1
            for _ in range(backoff):
                if not _running:
                    break
                time.sleep(1)
            backoff = min(backoff * 2, 300)

    mailbox.close()
    store.close()
    log.info("Agente detenido.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agente IA de atención por correo 24/7")
    parser.add_argument("--env-file", default=None, help="Ruta a un archivo .env")
    parser.add_argument("--once", action="store_true", help="Procesa la bandeja una vez y termina")
    parser.add_argument("--dry-run", action="store_true", help="No envía correos; solo registra")
    args = parser.parse_args(argv)

    try:
        cfg = Config.from_env(args.env_file)
    except RuntimeError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        return 2
    if args.dry_run:
        object.__setattr__(cfg, "dry_run", True)

    logging.basicConfig(
        level=getattr(logging, cfg.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    return run(cfg, once=args.once)


if __name__ == "__main__":
    sys.exit(main())
