# Despliegue en Incus (Linux) — Locutor

Guía concreta para desplegar dentro de un **contenedor de sistema Incus**.
Se recomienda **Ubuntu 24.04** porque trae **Python 3.12** de serie
(sherpa-onnx no tiene wheels para 3.13/3.14).

Todos los comandos se ejecutan **en el host** (donde está Incus), salvo donde se
indique. Sustituye `tu-dominio.com` por tu dominio real.

---

## 1. Crear el contenedor

```bash
incus launch images:ubuntu/24.04 locutor
```

## 2. Dependencias dentro del contenedor

```bash
incus exec locutor -- apt-get update
incus exec locutor -- apt-get install -y python3.12 python3.12-venv ffmpeg curl gpg

# Caddy (reverse proxy con HTTPS automático)
incus exec locutor -- bash -c '
  curl -1sLf "https://dl.cloudsmith.io/public/caddy/stable/gpg.key" | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf "https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt" > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update && apt-get install -y caddy'
```

## 3. Copiar e instalar la app

```bash
# Subir el paquete al contenedor y descomprimir en /opt
incus file push locutor-deploy.tar.gz locutor/root/
incus exec locutor -- tar -xzf /root/locutor-deploy.tar.gz -C /opt
#   -> /opt/locutor

# Bootstrap: crea el venv, instala dependencias y descarga las voces (~1 GB)
incus exec locutor -- bash -c "cd /opt/locutor && bash deploy/install.sh"
```

## 4. Configurar secretos y usuario

```bash
# Generar secretos
incus exec locutor -- /opt/locutor/.venv/bin/python -c "import secrets; print('SECRET_KEY=', secrets.token_urlsafe(48))"
incus exec locutor -- /opt/locutor/.venv/bin/python -c "import secrets; print('API_BEARER_TOKEN=', secrets.token_urlsafe(48))"

# Editar /opt/locutor/.env y pegar esos valores (entra con shell):
incus exec locutor -- bash       # dentro: cd /opt/locutor && vi .env ; exit
#   Deja COOKIE_SECURE=true y TRUST_PROXY=true

# Crear el primer usuario administrador
incus exec locutor -- bash -c "cd /opt/locutor && ./.venv/bin/python -m scripts.create_user --username admin --admin"
```

## 5. Servicio systemd (dentro del contenedor)

```bash
incus exec locutor -- useradd --system --home /opt/locutor locutor
incus exec locutor -- chown -R locutor:locutor /opt/locutor
incus exec locutor -- cp /opt/locutor/deploy/locutor.service /etc/systemd/system/
incus exec locutor -- systemctl daemon-reload
incus exec locutor -- systemctl enable --now locutor
incus exec locutor -- systemctl status locutor --no-pager
```

La app escucha solo en `127.0.0.1:8000` dentro del contenedor.

## 6. HTTPS con Caddy (dentro del contenedor)

```bash
incus exec locutor -- cp /opt/locutor/deploy/Caddyfile /etc/caddy/Caddyfile
# Edita el dominio:
incus exec locutor -- sed -i "s/tu-dominio.com/MIDOMINIO.com/" /etc/caddy/Caddyfile
incus exec locutor -- systemctl restart caddy
```

## 7. Exponer el contenedor a internet

Con la red NAT por defecto de Incus, reenvía los puertos 80/443 del host al
contenedor (necesario el 80 para el reto ACME de Let's Encrypt):

```bash
incus config device add locutor http  proxy listen=tcp:0.0.0.0:80  connect=tcp:127.0.0.1:80
incus config device add locutor https proxy listen=tcp:0.0.0.0:443 connect=tcp:127.0.0.1:443
```

> Si el contenedor está en una red **bridged** con IP propia y el DNS de tu
> dominio apunta directamente a esa IP, **no** necesitas estos `proxy devices`.

El **DNS** de `tu-dominio.com` debe apuntar a la IP pública del host. Caddy
obtendrá el certificado automáticamente al recibir la primera petición.

## 8. Comprobar

```bash
# Salud (desde el host, dentro del contenedor)
incus exec locutor -- curl -s http://127.0.0.1:8000/health
#   -> {"status":"ok","model_loaded":true,"voices":6}

# Desde fuera, con HTTPS
curl -s https://tu-dominio.com/health
```

Abre `https://tu-dominio.com`, inicia sesión y sube un documento de prueba.

---

## Operación

```bash
incus exec locutor -- journalctl -u locutor -f      # logs de la app (JSON)
incus exec locutor -- systemctl restart locutor     # reiniciar
incus exec locutor -- systemctl restart caddy       # recargar TLS/dominio
```

- **Recursos**: si limitas CPUs del contenedor (`incus config set locutor limits.cpu N`),
  ajusta `NUM_THREADS`/`CONCURRENCY` en `.env` para que `NUM_THREADS × CONCURRENCY ≤ N`.
- **Provider**: en Linux usa `PROVIDER=cpu` (CoreML es solo de macOS).
- **Copia de seguridad**: basta con `/opt/locutor/.env` y `/opt/locutor/data/locutor.db`
  (usuarios). Los modelos se vuelven a descargar con `scripts/download_voices.sh`.
- **Snapshot del contenedor** antes de actualizar: `incus snapshot create locutor pre-update`.
