#!/usr/bin/env bash
# Actualiza Locutor en un contenedor Incus. EJECUTAR EN EL HOST (donde está Incus),
# en la misma carpeta que el paquete locutor-deploy.tar.gz.
#
#   bash update.sh
#
# Variables opcionales (con sus valores por defecto):
#   CONTAINER=locutor  TARBALL=./locutor-deploy.tar.gz  APPDIR=/opt/locutor  SERVICE=locutor  bash update.sh
set -euo pipefail

CONTAINER="${CONTAINER:-locutor}"
TARBALL="${TARBALL:-locutor-deploy.tar.gz}"
APPDIR="${APPDIR:-/opt/locutor}"
SERVICE="${SERVICE:-locutor}"

[ -f "$TARBALL" ] || { echo "✗ No encuentro el paquete: $TARBALL"; exit 1; }
incus info "$CONTAINER" >/dev/null 2>&1 || { echo "✗ No existe el contenedor: $CONTAINER"; exit 1; }

echo "==> Subiendo $TARBALL al contenedor '$CONTAINER'"
incus file push "$TARBALL" "$CONTAINER/root/locutor-deploy.tar.gz"

echo "==> Extrayendo el código en $APPDIR (no toca .env, models/ ni data/)"
incus exec "$CONTAINER" -- tar -xzf /root/locutor-deploy.tar.gz -C "$(dirname "$APPDIR")"

echo "==> Ajustando permisos"
incus exec "$CONTAINER" -- chown -R locutor:locutor "$APPDIR" || true

echo "==> Reiniciando el servicio '$SERVICE'"
incus exec "$CONTAINER" -- systemctl restart "$SERVICE"

echo "==> Comprobando salud (espera unos segundos al arranque)"
sleep 3
incus exec "$CONTAINER" -- curl -s http://127.0.0.1:8000/health || true
echo
echo "✓ Actualización completada."
