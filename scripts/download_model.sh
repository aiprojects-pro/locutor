#!/usr/bin/env bash
# Descarga el modelo de voz en español VITS coqui-css10 de sherpa-onnx.
# Uso:  bash scripts/download_model.sh
set -euo pipefail

cd "$(dirname "$0")/.."
MODELS_DIR="models"
NAME="vits-coqui-es-css10"
URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/${NAME}.tar.bz2"

mkdir -p "$MODELS_DIR"
cd "$MODELS_DIR"

if [ -d "$NAME" ]; then
  echo "El modelo ya existe en ${MODELS_DIR}/${NAME}. Nada que hacer."
  exit 0
fi

echo "Descargando ${NAME}…"
curl -L --fail -o "${NAME}.tar.bz2" "$URL"
echo "Descomprimiendo…"
tar xjf "${NAME}.tar.bz2"
rm -f "${NAME}.tar.bz2"

echo "Listo. Configura en .env:  MODEL_DIR=$(pwd)/${NAME}"
ls -la "$NAME"
