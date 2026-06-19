#!/usr/bin/env bash
# Bootstrap de instalación de Locutor. Ejecutar desde la raíz del proyecto:
#   bash deploy/install.sh
# Idempotente: se puede volver a ejecutar sin problema.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Comprobando dependencias del sistema"
command -v ffmpeg >/dev/null || { echo "FALTA ffmpeg. Instálalo (macOS: brew install ffmpeg | Debian/Ubuntu: apt-get install -y ffmpeg)"; exit 1; }

PY="${PYTHON:-python3.12}"
command -v "$PY" >/dev/null || { echo "FALTA $PY. Instala Python 3.12 (sherpa-onnx no tiene wheel para 3.13/3.14)."; exit 1; }

echo "==> Creando entorno virtual (.venv)"
[ -d .venv ] || "$PY" -m venv .venv
./.venv/bin/python -m pip install --upgrade pip >/dev/null
echo "==> Instalando dependencias de Python"
./.venv/bin/pip install -e . >/dev/null
./.venv/bin/python -c "import sherpa_onnx; print('   sherpa-onnx', sherpa_onnx.__version__)"

echo "==> Descargando voces (si faltan)"
bash scripts/download_voices.sh

echo "==> Configuración"
if [ ! -f .env ]; then
  cp deploy/.env.production.example .env
  echo "   Creado .env desde la plantilla de producción. EDÍTALO y pon SECRET_KEY/API_BEARER_TOKEN."
else
  echo "   .env ya existe (no se toca)."
fi

echo
echo "Instalación lista. Siguientes pasos:"
echo "  1) Edita .env (SECRET_KEY, API_BEARER_TOKEN, dominio/seguridad)."
echo "  2) Crea el primer usuario:  ./.venv/bin/python -m scripts.create_user --username admin --admin"
echo "  3) Arranca el servicio (ver deploy/ + DEPLOY.md) detrás de Caddy (HTTPS)."
