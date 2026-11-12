#!/usr/bin/env bash
# Instalación en Debian 13 (trixie). Ejecutar como root:  sudo bash deploy/install.sh
set -euo pipefail

APP_DIR=/opt/agente-email-ia
APP_USER=agente

if [[ $EUID -ne 0 ]]; then
  echo "Ejecuta con sudo/root." >&2; exit 1
fi

echo "==> Instalando dependencias del sistema"
apt-get update
apt-get install -y python3 python3-venv python3-pip git rsync ca-certificates

echo "==> Creando usuario de servicio"
id -u "$APP_USER" &>/dev/null || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"

echo "==> Copiando aplicación a $APP_DIR"
mkdir -p "$APP_DIR"
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
rsync -a --exclude '.git' --exclude '.venv' --exclude 'data' --exclude '.env' "$SRC_DIR"/ "$APP_DIR"/
mkdir -p "$APP_DIR/data"

echo "==> Creando entorno virtual e instalando"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install "$APP_DIR"

if [[ ! -f "$APP_DIR/.env" ]]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  echo "==> Se creó $APP_DIR/.env : EDÍTALO con tus credenciales antes de iniciar."
fi

chown -R "$APP_USER":"$APP_USER" "$APP_DIR"
chmod 600 "$APP_DIR/.env"

echo "==> Instalando servicio systemd"
cp "$APP_DIR/deploy/agente-email.service" /etc/systemd/system/agente-email.service
systemctl daemon-reload
systemctl enable agente-email.service

cat <<'EOF'

Listo. Siguientes pasos:
  1) sudo nano /opt/agente-email-ia/.env        (credenciales; deja DRY_RUN=true para probar)
  2) sudo nano /opt/agente-email-ia/config/knowledge_base.md
  3) sudo systemctl start agente-email
  4) sudo journalctl -u agente-email -f          (ver logs)
  5) Cuando las respuestas simuladas se vean bien: DRY_RUN=false y  sudo systemctl restart agente-email
EOF
