from email import message_from_string, policy

from agente_email.ai import parse_model_output
from agente_email.mailbox import _strip_quoted, extract_body
from agente_email.safety import ignore_reason
from agente_email.store import Store

OWN = "atencion@empresa.com"


def mk(headers: str, body: str = "Hola") -> object:
    return message_from_string(headers.strip() + "\n\n" + body, policy=policy.default)


def test_normal_customer_email_is_answered():
    m = mk("From: Ana <ana@gmail.com>\nSubject: Consulta\nContent-Type: text/plain")
    assert ignore_reason(m, OWN) is None


def test_ignores_self_noreply_and_auto():
    assert ignore_reason(mk("From: atencion@empresa.com\nSubject: x"), OWN)
    assert ignore_reason(mk("From: no-reply@shop.com\nSubject: x"), OWN)
    assert ignore_reason(mk("From: a@b.com\nSubject: x\nAuto-Submitted: auto-replied"), OWN)
    assert ignore_reason(mk("From: a@b.com\nSubject: x\nPrecedence: bulk"), OWN)
    assert ignore_reason(mk("From: a@b.com\nSubject: x\nList-Unsubscribe: <mailto:u@b.com>"), OWN)
    assert ignore_reason(mk("From: a@b.com\nSubject: Respuesta automática: vacaciones"), OWN)


def test_auto_submitted_no_is_allowed():
    assert ignore_reason(mk("From: a@b.com\nSubject: hola\nAuto-Submitted: no"), OWN) is None


def test_store_dedup_and_limits():
    s = Store(":memory:")
    assert not s.seen("<1@x>")
    s.mark("<1@x>", "A@B.com", "hola", "replied")
    assert s.seen("<1@x>")
    assert s.replies_since("a@b.com") == 1
    assert s.total_replies_since() == 1
    s.mark("<2@x>", "a@b.com", "x", "failed")
    assert not s.seen("<2@x>")  # los fallidos se reintentan
    s.mark("<3@x>", "a@b.com", "x", "gave_up")
    assert s.seen("<3@x>")


def test_parse_model_output_json_and_fallback():
    ok = parse_model_output('```json\n{"reply":"Hola","confidence":"high","reason":"ok"}\n```')
    assert ok.text == "Hola" and ok.confidence == "high"
    bad = parse_model_output("Respuesta sin JSON")
    assert bad.confidence == "low" and bad.text == "Respuesta sin JSON"


def test_strip_quoted_history():
    text = "Gracias!\n\n> texto citado\nEl lun, 1 nov escribió:\nmás historial"
    assert _strip_quoted(text) == "Gracias!"


def test_extract_body_prefers_plain():
    m = message_from_string(
        "From: a@b.com\nSubject: s\nMIME-Version: 1.0\n"
        'Content-Type: multipart/alternative; boundary="B"\n\n'
        "--B\nContent-Type: text/plain\n\nTexto plano\n"
        "--B\nContent-Type: text/html\n\n<p>HTML</p>\n--B--\n",
        policy=policy.default,
    )
    assert extract_body(m, 1000) == "Texto plano"
