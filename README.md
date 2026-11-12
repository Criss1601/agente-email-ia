# Agente IA de atención por correo (24/7)

Agente autónomo que lee la bandeja de entrada, redacta la respuesta con Claude usando tu base de
conocimiento y la envía por SMTP, todo el día y todos los días, sin intervención humana.

## Cómo funciona

```
IMAP (correos no leídos) → filtros anti-bucle/spam → límites por remitente
        → Claude + base de conocimiento → SMTP (respuesta en el mismo hilo) → SQLite (auditoría)
```

- **Autónomo**: corre como servicio systemd (`Restart=always`), se reconecta solo con backoff exponencial.
- **Sin inventar**: solo responde con `config/knowledge_base.md`; si falta información lo dice con honestidad.
- **Anti-bucle**: ignora no-reply, listas, rebotes y autorrespuestas; sus correos llevan `Auto-Submitted: auto-replied`.
- **Límites**: máximo de respuestas por remitente y totales por día.
- **Seguro ante prompt injection**: el correo del cliente se trata como datos, no como instrucciones.
- **Idempotente**: nunca responde dos veces al mismo `Message-ID`.

## Instalación en Debian 13

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/TU_USUARIO/agente-email-ia.git
cd agente-email-ia
sudo bash deploy/install.sh
sudo nano /opt/agente-email-ia/.env                      # credenciales
sudo nano /opt/agente-email-ia/config/knowledge_base.md  # tu información real
sudo systemctl start agente-email
sudo journalctl -u agente-email -f
```

Empieza con `DRY_RUN=true`: el agente registra en el log lo que respondería sin enviar nada.
Cuando las respuestas se vean bien, cambia a `DRY_RUN=false` y ejecuta `sudo systemctl restart agente-email`.

### Con Docker (alternativa)

```bash
cp .env.example .env && nano .env
docker compose up -d --build
```

## Desarrollo local

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
cp .env.example .env
agente-email --once --dry-run      # procesa la bandeja una vez sin enviar
```

## Gmail / Google Workspace

Activa la verificación en dos pasos, crea una **contraseña de aplicación** y úsala en `EMAIL_PASSWORD`.
Host IMAP `imap.gmail.com` (993), SMTP `smtp.gmail.com` (465, `ssl`).

## Subir a GitHub

```bash
git remote add origin https://github.com/TU_USUARIO/agente-email-ia.git
git push -u origin main
```

`.env` y `data/` están en `.gitignore`: tus credenciales nunca se suben.

## Buenas prácticas para operar sin supervisión

- Mantén la base de conocimiento completa y actualizada: es lo que evita respuestas inventadas.
- Usa una cuenta de correo dedicada (p. ej. `atencion@…`), no la personal.
- Configura `ESCALATION_EMAIL` si quieres recibir copia de las respuestas de baja confianza (opcional).
- Revisa de vez en cuando la tabla `processed` en `data/agente.db` (auditoría de todo lo respondido).
- Define un tope de gasto en tu cuenta de Anthropic.

## Licencia

MIT
