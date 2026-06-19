"""Rutas web (UI con sesión por cookie): login, panel, subida y descarga."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.docs.extract import UnsupportedFileError, extract_text
from app.security.auth import authenticate, create_session_token, get_current_user
from app.security.csrf import get_or_create_csrf, verify_csrf
from app.security.ratelimit import client_ip, login_ip_limiter, tts_user_limiter
from app.logging_conf import get_logger

router = APIRouter()
_settings = get_settings()
logger = get_logger("locutor.web")
templates = Jinja2Templates(directory="app/templates")


def _set_session_cookies(response, token: str, csrf_token: str) -> None:
    response.set_cookie(
        _settings.session_cookie_name, token,
        max_age=_settings.session_max_age_s, httponly=True,
        secure=_settings.cookie_secure, samesite="lax", path="/",
    )
    response.set_cookie(
        _settings.csrf_cookie_name, csrf_token,
        max_age=_settings.session_max_age_s, httponly=False,
        secure=_settings.cookie_secure, samesite="lax", path="/",
    )


def require_user(request: Request):
    user = get_current_user(request)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No autenticado.")
    return user


# --- Login / logout ------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if get_current_user(request):
        return RedirectResponse("/", status_code=302)
    csrf_token = get_or_create_csrf(request)
    response = templates.TemplateResponse(
        request, "login.html", {"csrf_token": csrf_token, "error": None}
    )
    response.set_cookie(
        _settings.csrf_cookie_name, csrf_token, max_age=_settings.session_max_age_s,
        httponly=False, secure=_settings.cookie_secure, samesite="lax", path="/",
    )
    return response


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    username: str = Form(..., max_length=64),
    password: str = Form(..., max_length=256),
    csrf_token: str | None = Form(None),
):
    verify_csrf(request, csrf_token)
    ip = client_ip(request)

    if not login_ip_limiter.hit(ip):
        logger.warning("rate limit login", extra={"event": "login_ratelimit", "ip": ip})
        new_csrf = get_or_create_csrf(request)
        resp = templates.TemplateResponse(
            request, "login.html",
            {"csrf_token": new_csrf,
             "error": "Demasiados intentos. Espera unos minutos."},
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
        resp.set_cookie(_settings.csrf_cookie_name, new_csrf, httponly=False,
                        secure=_settings.cookie_secure, samesite="lax", path="/")
        return resp

    result = authenticate(username.strip(), password)
    if result.user is None:
        logger.info("login fallido", extra={"event": "login_failed", "ip": ip, "user": username})
        new_csrf = get_or_create_csrf(request)
        resp = templates.TemplateResponse(
            request, "login.html",
            {"csrf_token": new_csrf, "error": result.error},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
        resp.set_cookie(_settings.csrf_cookie_name, new_csrf, httponly=False,
                        secure=_settings.cookie_secure, samesite="lax", path="/")
        return resp

    logger.info("login ok", extra={"event": "login_ok", "ip": ip, "user": result.user.username})
    token = create_session_token(result.user.id)
    new_csrf = get_or_create_csrf(request)
    response = RedirectResponse("/", status_code=302)
    _set_session_cookies(response, token, new_csrf)
    return response


@router.post("/logout")
def logout(request: Request, csrf_token: str | None = Form(None)):
    verify_csrf(request, csrf_token)
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie(_settings.session_cookie_name, path="/")
    return response


# --- Panel principal -----------------------------------------------------

@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    user = get_current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=302)
    csrf_token = get_or_create_csrf(request)
    jobs = request.app.state.jobs.list_for_user(user.id)
    response = templates.TemplateResponse(
        request, "dashboard.html",
        {"user": user, "csrf_token": csrf_token,
         "jobs": [j.public() for j in jobs],
         "voices": request.app.state.engine.list_voices(),
         "max_files": _settings.max_files_per_request,
         "max_mb": _settings.max_upload_bytes // (1024 * 1024)},
    )
    response.set_cookie(_settings.csrf_cookie_name, csrf_token, httponly=False,
                        secure=_settings.cookie_secure, samesite="lax", path="/")
    return response


# --- Subida y generación -------------------------------------------------

@router.post("/upload")
async def upload(
    request: Request,
    files: list[UploadFile] = File(...),
    csrf_token: str | None = Form(None),
    voice: str | None = Form(None),
    speed: float = Form(_settings.default_speed),
    user=Depends(require_user),
):
    verify_csrf(request, csrf_token)

    # Rechazo temprano por tamaño declarado (antes de leer nada en memoria).
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > _settings.max_total_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            "El tamaño total de los archivos es excesivo.")

    if not tts_user_limiter.hit(f"user:{user.id}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Has alcanzado el límite de generaciones por minuto.")

    if not files:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No se han enviado archivos.")
    if len(files) > _settings.max_files_per_request:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Máximo {_settings.max_files_per_request} archivos por solicitud.")
    if not (0.1 < speed <= 3.0):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Velocidad inválida.")
    # Resuelve la voz (si es inválida o no se envía, usa la voz por defecto).
    voice_key = request.app.state.engine.resolve(voice).key

    texts: list[str] = []
    names: list[str] = []
    total_bytes = 0
    for f in files:
        data = await f.read()
        total_bytes += len(data)
        if len(data) > _settings.max_upload_bytes:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                f"'{f.filename}' supera el tamaño máximo permitido.")
        if total_bytes > _settings.max_total_upload_bytes:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                "El tamaño total de los archivos es excesivo.")
        try:
            text = extract_text(f.filename or "", data)
        except UnsupportedFileError as exc:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc))
        except Exception:
            logger.exception("error extrayendo texto", extra={"event": "extract_error"})
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"No se pudo leer el contenido de '{f.filename}'.")
        if text.strip():
            texts.append(text.strip())
            names.append(f.filename or "documento")

    combined = "\n\n".join(texts).strip()
    if not combined:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Los documentos no contienen texto legible.")
    if len(combined) > _settings.max_input_chars:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"El texto supera el máximo de {_settings.max_input_chars} caracteres.")

    source = names[0] if len(names) == 1 else f"{len(names)} documentos"
    job = request.app.state.jobs.create(user.id, combined, source, voice_key, speed)
    logger.info("trabajo creado", extra={"job_id": job.id, "event": "job_created",
                                         "user": user.username})
    return JSONResponse(job.public(), status_code=status.HTTP_202_ACCEPTED)


@router.get("/jobs/{job_id}")
def job_status(request: Request, job_id: str, user=Depends(require_user)):
    job = request.app.state.jobs.get(job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trabajo no encontrado.")
    return JSONResponse(job.public())


@router.get("/jobs/{job_id}/download")
def job_download(request: Request, job_id: str, user=Depends(require_user)):
    job = request.app.state.jobs.get(job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trabajo no encontrado.")
    if job.status != "done" or not job.mp3_path or not job.mp3_path.exists():
        raise HTTPException(status.HTTP_409_CONFLICT, "El audio aún no está disponible.")
    return FileResponse(
        path=str(job.mp3_path), media_type="audio/mpeg",
        filename=f"{job.source_name}.mp3".replace("/", "_"),
    )
