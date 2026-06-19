#!/usr/bin/env bash
# Descarga TODAS las voces del catálogo (config/voices.yaml) en models/.
# Uso:  bash scripts/download_voices.sh
set -euo pipefail
cd "$(dirname "$0")/.."

BASE="https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models"
MODELS_DIR="models"
mkdir -p "$MODELS_DIR"

# Modelos usados por config/voices.yaml (Sharvard aporta 2 locutores).
VOICES=(
  vits-piper-es_ES-sharvard-medium
  vits-piper-es_ES-davefx-medium
  vits-coqui-es-css10
  vits-piper-es_AR-daniela-high
  vits-piper-es_MX-claude-high
)

for n in "${VOICES[@]}"; do
  if [ -d "$MODELS_DIR/$n" ]; then
    echo "✓ ya existe: $n"
    continue
  fi
  echo "↓ descargando $n ..."
  curl -L --fail -o "$MODELS_DIR/$n.tar.bz2" "$BASE/$n.tar.bz2"
  tar xjf "$MODELS_DIR/$n.tar.bz2" -C "$MODELS_DIR"
  rm -f "$MODELS_DIR/$n.tar.bz2"
  echo "✓ instalado: $n"
done

echo
echo "Voces instaladas en $MODELS_DIR/:"
ls -d "$MODELS_DIR"/*/
