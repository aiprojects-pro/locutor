# Guía de despliegue — Locutor

Para el administrador de sistemas. Pone la aplicación en producción detrás de
HTTPS, como servicio del sistema, en **un único proceso** uvicorn.

> ⚠️ **Constante de arquitectura:** ejecutar **un solo proceso** uvicorn (sin
> `--workers`). El modelo de voz, el control de concurrencia y el rate-limiter son
> estado global en memoria. La capacidad se escala con la concurrencia interna
> (`CONCURRENCY`/`NUM_THREADS`), no con más procesos.

> 🐧 **¿Despliegas en Incus?** Hay una guía con comandos copia-pega específicos en
> **[deploy/INCUS.md](deploy/INCUS.md)**. Esta guía general cubre Linux (systemd) y macOS (launchd).

---

## 1. Requisitos del servidor

- **Python 3.12** (sherpa-onnx no publica wheels para 3.13/3.14).
- **ffmpeg** (para MP3).
- **Caddy** (reverse proxy con HTTPS automático) — o nginx con tu propio TLS.
- ~2 GB de RAM libres (carga 5 modelos de voz) y ~1 GB de disco para los modelos.
- Salida a internet para la descarga inicial de modelos (luego funciona offline).

Instalación de dependencias del sistema:

```bash
# macOS (Mac Mini M4 — objetivo del proyecto)
brew install python@3.12 ffmpeg caddy

# Debian/Ubuntu
sudo apt-get update && sudo apt-get install -y python3.12 python3.12-venv ffmpeg
#   Caddy: https://caddyserver.com/docs/install
```

## 2. Instalar la aplicación

Copia el proyecto al servidor (p. ej. `/opt/locutor` en Linux o
`/Users/Shared/locutor` en macOS) y ejecuta el bootstrap:

```bash
cd /opt/locutor          # o /Users/Shared/locutor
bash deploy/install.sh   # crea .venv, instala deps y descarga las voces
```

## 3. Configurar (`.env`)

`install.sh` crea un `.env` a partir de [deploy/.env.production.example](deploy/.env.production.example).
Edítalo y, como mínimo:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"   # -> SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(48))"   # -> API_BEARER_TOKEN
```

Deja en producción: `COOKIE_SECURE=true` y `TRUST_PROXY=true` (hay Caddy delante).

## 4. Crear usuarios

El registro abierto está deshabilitado a propósito. Crea usuarios por CLI:

```bash
./.venv/bin/python -m scripts.create_user --username admin --admin
./.venv/bin/python -m scripts.create_user --username locutor1
```

## 5. Ejecutar como servicio

### Linux (systemd)

```bash
sudo useradd --system --home /opt/locutor locutor || true
sudo chown -R locutor:locutor /opt/locutor
sudo cp deploy/locutor.service /etc/systemd/system/locutor.service
sudo systemctl daemon-reload
sudo systemctl enable --now locutor
journalctl -u locutor -f          # logs en vivo
```

### macOS (launchd)

```bash
sudo cp deploy/com.locutor.app.plist /Library/LaunchDaemons/
sudo launchctl load -w /Library/LaunchDaemons/com.locutor.app.plist
sudo launchctl list | grep locutor
```

La app queda escuchando solo en `127.0.0.1:8000` (no expuesta directamente).

## 6. HTTPS con Caddy

Edita el dominio en [deploy/Caddyfile](deploy/Caddyfile) (DNS del dominio
apuntando al servidor) y arráncalo:

```bash
# Prueba en primer plano
caddy run --config deploy/Caddyfile
# Como servicio:  https://caddyserver.com/docs/running
```

Caddy obtiene el certificado automáticamente y reenvía a la app. **Sin TLS, las
cookies de sesión y el token de la API viajarían en claro: no lo expongas sin HTTPS.**

## 7. Comprobación post-despliegue

```bash
curl -s https://tu-dominio.com/health      # {"status":"ok","model_loaded":true,"voices":6}
```

Luego abre `https://tu-dominio.com`, inicia sesión y sube un documento de prueba.

## 8. Operación

- **Logs**: salida JSON estructurada (systemd: `journalctl -u locutor`; macOS:
  `data/stdout.log` / `data/stderr.log`). No contienen secretos ni el texto.
- **Datos**: SQLite de usuarios y audios temporales en `data/` (se purgan a las 24 h).
- **Actualizar**: reemplaza el código, `./.venv/bin/pip install -e .`, reinicia el servicio.
- **Voces**: catálogo en [config/voices.yaml](config/voices.yaml); añadir/quitar voces
  no requiere tocar código (descargar el modelo en `models/` y editar el YAML).
- **Rendimiento**: mide `cpu` vs `coreml` y `NUM_THREADS` con
  `./.venv/bin/python -m scripts.bench` y fija `PROVIDER`/`NUM_THREADS` en `.env`.
