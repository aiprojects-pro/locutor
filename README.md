# 🎙️ Locutor — Texto a voz (TTS) en español

Aplicación web segura que permite **iniciar sesión**, **subir uno o varios documentos
`.pdf` o `.docx`**, locutar todo su texto en español con **sherpa-onnx (`OfflineTts`)**
y **descargar el audio en MP3**, reproducible desde cualquier dispositivo.

Pensada para ejecutarse en un **Mac Mini Apple Silicon (M4 / M4 Max)**.

---

## Arquitectura en 30 segundos

```
Navegador ── HTTPS ──► Caddy (TLS) ──► uvicorn (1 proceso) ──► FastAPI
                                                               │
   login (sesión cookie) ┐                                     ├─ extracción .pdf/.docx
   subida de documentos  ┘                                     ├─ normalización (num2words, moneda…)
                                                               ├─ troceo por frases
   API Bearer ───────────────────────────────────────────────►├─ TTS sherpa-onnx (pool, carga única)
                                                               └─ ensamblado + MP3 (ffmpeg)
```

- **Un solo proceso uvicorn.** El modelo, el semáforo de concurrencia y el rate
  limiter son **estado global en memoria**. El rendimiento se escala con
  **concurrencia async interna**, NO con `--workers`. No lances varios workers.
- El motor produce audio crudo (WAV/PCM); el **MP3** se obtiene transcodificando
  con **ffmpeg** (mono, 128 kbps por defecto).
- Procesamiento por **trabajos en segundo plano** con barra de progreso; el audio
  se genera frase a frase, se ensambla **en orden** y se ofrece como descarga MP3
  (no hay streaming progresivo — ver "Decisiones" más abajo).

---

## Requisitos

- **Python 3.12** (recomendado). El enunciado pedía 3.14, pero **sherpa-onnx aún no
  publica wheels para 3.14**; con 3.12 la instalación es directa (verificado:
  `sherpa-onnx 1.13.3`). Si en el futuro hay wheel para 3.14, puede reconsiderarse.
- **ffmpeg** (para MP3): `brew install ffmpeg`.
- El **modelo de voz** `vits-coqui-es-css10` (descargable con un script).

## Instalación

```bash
# 1) Dependencias del sistema
brew install python@3.12 ffmpeg

# 2) Entorno virtual + dependencias del proyecto
python3.12 -m venv .venv
./.venv/bin/pip install -e .            # o: pip install -e ".[dev]" para tests

# 3) Voces en español (descarga todo el catálogo en ./models)
bash scripts/download_voices.sh         # ~1 GB; voces de config/voices.yaml

# 4) Configuración
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # pega esto en SECRET_KEY

# 5) Crea tu primer usuario (administrador)
./.venv/bin/python -m scripts.create_user --username admin --admin
```

## Ejecución

```bash
# UN solo proceso (no usar --workers)
./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Para desarrollo local sin HTTPS, pon `COOKIE_SECURE=false` y `TRUST_PROXY=false`
en `.env` y abre http://127.0.0.1:8000.

### Producción (servidor, para el administrador de sistemas)

Guía completa en **[DEPLOY.md](DEPLOY.md)**: instalación, servicio del sistema
(systemd en Linux / launchd en macOS), HTTPS con Caddy y comprobaciones. La carpeta
[deploy/](deploy/) incluye `install.sh`, `Caddyfile`, las unidades de servicio y
`.env.production.example`.

Resumen: TLS termina en un reverse proxy (Caddy) delante de la app; en `.env`
`COOKIE_SECURE=true` y `TRUST_PROXY=true`.

> ⚠️ **Sin TLS, el token de la API y las cookies de sesión viajan en texto plano.**
> No expongas la app a internet sin HTTPS por delante.

---

## Seguridad implementada

| Área | Medida |
|------|--------|
| Contraseñas | Hash **Argon2** (`argon2-cffi`), rehash automático |
| Sesión | Cookie **firmada** (itsdangerous), `HttpOnly` + `Secure` + `SameSite=Lax`, caducidad |
| CSRF | Token *double-submit* firmado en todos los POST |
| Fuerza bruta | Rate-limit de login por IP + **bloqueo de cuenta** tras N fallos |
| Abuso TTS | Rate-limit de trabajos por usuario/min |
| Cabeceras | CSP estricta, HSTS, `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy` |
| Subidas | Validación por **magic bytes** (no solo extensión), tamaño máx. por archivo y total, límite de caracteres, limpieza de temporales |
| API | `Authorization: Bearer` con `hmac.compare_digest`; whitelist por IP del socket (opcional) |
| Mensajes | Login genérico (no revela si el usuario existe); secretos nunca se registran |
| Logs | Estructurados en JSON, **sin secretos ni contenido de documentos** |

El **registro abierto está deshabilitado** por diseño: los usuarios se crean con
`scripts/create_user.py`.

### Endpoint API (máquina a máquina)

```bash
curl -X POST http://127.0.0.1:8000/api/tts \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"Hola mundo. Son las 14:30.","voice":"sharvard-f","speed":1.0}' \
  --output salida.wav     # WAV PCM_16 lossless; sample rate en cabecera X-Sample-Rate
```

`/health` está abierto y devuelve el estado del modelo.

---

## Voces (multivoz)

Las voces seleccionables se definen en [config/voices.yaml](config/voices.yaml). Cada
entrada apunta a una carpeta dentro de `models/` y a un locutor (`sid`); varias
voces pueden compartir el mismo modelo (p. ej. **Sharvard** tiene un locutor
femenino `sid 1` y otro masculino `sid 0`). En el panel aparece un desplegable
para elegir la voz por documento; la API acepta el campo `voice` (ver `GET /voices`).

Voces incluidas por defecto (todas en español, offline):

| Clave | Voz | |
|-------|-----|---|
| `sharvard-f` | 🇪🇸 España · Sharvard femenina | **por defecto** |
| `sharvard-m` | 🇪🇸 España · Sharvard masculina | |
| `davefx` | 🇪🇸 España · Davefx masculina | |
| `css10` | 🇪🇸 España · CSS10 (grave) | |
| `daniela` | 🇦🇷 Argentina · Daniela femenina | |
| `claude` | 🇲🇽 México · Claude | |

Cada **modelo distinto** se carga una vez en su propio pool (tamaño = `CONCURRENCY`)
y se calienta al arrancar. Para añadir o quitar voces, edita `voices.yaml` y, si hace
falta, descarga el modelo en `models/`. Para cambiar la voz por defecto, ajusta el
campo `default` de ese archivo.

## Rendimiento y concurrencia

- El modelo se **carga una vez** al arrancar y se hace **warm-up** con una frase.
- Para no asumir que `OfflineTts.generate()` es seguro en concurrencia, se usa un
  **pool de instancias** (tamaño = `CONCURRENCY`); cada generación toma una y la
  devuelve. Conservador (más RAM); si un benchmark confirma que una sola instancia
  es segura, baja `CONCURRENCY`/pool a 1.
- Regla anti sobre-suscripción: **`NUM_THREADS × CONCURRENCY ≤ núcleos de
  rendimiento`**. En M4 Max (~10 P): `4 × 2 = 8`.
- Un timeout por fragmento **no cancela** la generación nativa en curso (solo
  devuelve error al cliente). Por eso el trabajo real se **acota** con
  `CHUNK_MAX_CHARS` y `MAX_INPUT_CHARS`.

### Benchmark CoreML vs CPU (medir, no asumir)

`PROVIDER` admite `cpu` o `coreml`. **Cuál es más rápido depende del modelo y la
versión de onnxruntime; hay que medirlo.**

```bash
# Mide con CPU
PROVIDER=cpu NUM_THREADS=4 ./.venv/bin/python -m scripts.bench   # (script opcional a tu medida)
# Mide con CoreML
PROVIDER=coreml ./.venv/bin/python -m scripts.bench
```

Prueba también distintos `NUM_THREADS` (p. ej. 2, 4, 6) y quédate con la mejor
combinación para tu hardware.

---

## Decisiones de diseño (según el spec)

- **Estrategia de streaming:** se eligió **(a) generación por frase + ensamblado
  completo en orden → MP3 de descarga**. No hay streaming progresivo, por lo que
  los fragmentos **sí** pueden generarse en paralelo por el pool (el orden se
  preserva por índice). No se combina chunking paralelo con streaming progresivo.
- **MP3 vs lossless:** la web entrega **MP3** (universal). La API entrega **WAV
  PCM_16** sin pérdidas con el sample rate en cabecera, para que el cliente lo
  transcodifique a lo que quiera (Ogg/Vorbis, etc.).
- **Whitelist por IP:** configurable y **desactivada por defecto**, porque una app
  pública tiene muchas IPs de cliente. Útil para limitar el acceso a `/api/tts`.

---

## Tests

```bash
./.venv/bin/python -m pytest
```

Cubren normalización (números, decimales con ceros, negativos, %, moneda con
plurales y céntimos), troceo por frases (respeta `¿ ¡` y abreviaturas) y
extracción/validación de documentos.

## Estructura

```
app/            código (config, security, db, docs, tts, jobs, api, templates, static)
config/         normalization.yaml (reglas editables)
scripts/        create_user.py, download_model.sh
tests/          pruebas unitarias
Caddyfile       reverse proxy con HTTPS automático
.env.example    configuración de referencia
```
