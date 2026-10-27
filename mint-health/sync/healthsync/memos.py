"""Journal vocal : mémos enregistrés depuis l'applet Mint, le téléphone Android ou le navigateur.

Les fichiers audio sont dans MEMO_DIR (volume Docker), les métadonnées dans la table
voice_memos (lue par Grafana). Sur le serveur, tout passe derrière le mot de passe de Caddy.
"""
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field

from . import config, store

router = APIRouter(prefix="/memos", tags=["journal vocal"])

MEMO_DIR = Path(os.environ.get("MEMO_DIR", "/data/memos"))
MAX_BYTES = int(os.environ.get("MEMO_MAX_MB", "100")) * 1024 * 1024
DEVICES = {"android", "mint", "web"}
ID_RE = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$")
EXT = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/opus": "opus",
    "audio/mp4": "m4a",
    "audio/aac": "aac",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS voice_memos (
    id          text PRIMARY KEY,
    recorded_at timestamptz      NOT NULL,
    duration_s  double precision,
    title       text             NOT NULL,
    device      text             NOT NULL DEFAULT 'web',
    mime        text             NOT NULL,
    size_bytes  bigint           NOT NULL,
    created_at  timestamptz      NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS voice_memos_recorded_at ON voice_memos (recorded_at DESC);
"""


async def init() -> None:
    MEMO_DIR.mkdir(parents=True, exist_ok=True)
    async with await store.connect() as conn:
        await conn.execute(SCHEMA)


def _base_mime(content_type: str | None) -> str:
    return (content_type or "").split(";")[0].strip().lower()


def _path(memo_id: str, mime: str) -> Path:
    return MEMO_DIR / f"{memo_id}.{EXT.get(mime, 'bin')}"


def _check_id(memo_id: str) -> None:
    if not ID_RE.match(memo_id):
        raise HTTPException(404, "Mémo introuvable")


def default_title(at: datetime) -> str:
    local = at.astimezone(config.TZ)
    jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    mois = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
    return f"{jours[local.weekday()]} {local.day} {mois[local.month - 1]} · {local:%H:%M}"


def _row(r) -> dict:
    memo_id, recorded_at, duration, title, device, mime, size = r
    return {
        "id": memo_id,
        "recorded_at": recorded_at.isoformat(),
        "duration_s": duration,
        "title": title,
        "device": device,
        "mime": mime,
        "size_bytes": size,
        "audio": f"memos/{memo_id}/audio",
    }


COLS = "id, recorded_at, duration_s, title, device, mime, size_bytes"


@router.post("", status_code=201)
async def upload(
    request: Request,
    title: str | None = Query(None, max_length=120),
    duration: float | None = Query(None, ge=0, le=86400),
    device: str = Query("web"),
    recorded_at: datetime | None = Query(None),
):
    """Corps de la requête = le fichier audio brut (Content-Type audio/…)."""
    mime = _base_mime(request.headers.get("content-type"))
    if mime not in EXT:
        raise HTTPException(415, f"Format audio non pris en charge : {mime or 'inconnu'}")
    if device not in DEVICES:
        raise HTTPException(400, f"device doit être l'un de : {', '.join(sorted(DEVICES))}")
    at = recorded_at or datetime.now(timezone.utc)
    if at.tzinfo is None:
        at = at.replace(tzinfo=config.TZ)

    memo_id = f"{at.astimezone(config.TZ):%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"
    path = _path(memo_id, mime)
    tmp = path.with_suffix(".part")
    size = 0
    try:
        with tmp.open("wb") as f:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, f"Mémo trop gros (max {MAX_BYTES // 1024 // 1024} Mo)")
                f.write(chunk)
        if size == 0:
            raise HTTPException(400, "Fichier vide")
        tmp.rename(path)
    finally:
        tmp.unlink(missing_ok=True)

    clean_title = (title or "").strip() or default_title(at)
    async with await store.connect() as conn:
        await conn.execute(
            f"INSERT INTO voice_memos ({COLS}) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (memo_id, at, duration, clean_title, device, mime, size),
        )
    return _row((memo_id, at, duration, clean_title, device, mime, size))


@router.get("")
async def list_memos(limit: int = Query(50, ge=1, le=500)):
    async with await store.connect() as conn:
        cur = await conn.execute(
            f"SELECT {COLS} FROM voice_memos ORDER BY recorded_at DESC LIMIT %s", (limit,)
        )
        return [_row(r) for r in await cur.fetchall()]


async def _get(memo_id: str):
    _check_id(memo_id)
    async with await store.connect() as conn:
        cur = await conn.execute(f"SELECT {COLS} FROM voice_memos WHERE id = %s", (memo_id,))
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Mémo introuvable")
    return row


@router.get("/app", response_class=HTMLResponse)
async def app_page():
    """Enregistreur pour le téléphone (à ajouter à l'écran d'accueil) et le navigateur."""
    return HTMLResponse(APP_HTML)


@router.get("/manifest.webmanifest")
async def manifest():
    return Response(MANIFEST, media_type="application/manifest+json")


@router.get("/icon.svg")
async def icon():
    return Response(ICON_SVG, media_type="image/svg+xml", headers={"Cache-Control": "max-age=86400"})


@router.get("/{memo_id}/audio")
async def audio(memo_id: str):
    row = await _get(memo_id)
    path = _path(memo_id, row[5])
    if not path.exists():
        raise HTTPException(404, "Fichier audio absent")
    ext = path.suffix
    safe = re.sub(r"[^\w .-]+", "", row[3]).strip() or memo_id
    return FileResponse(path, media_type=row[5], filename=f"{safe}{ext}",
                        content_disposition_type="inline")


class Patch(BaseModel):
    title: str = Field(min_length=1, max_length=120)


@router.patch("/{memo_id}")
async def rename(memo_id: str, body: Patch):
    row = await _get(memo_id)
    title = body.title.strip()
    async with await store.connect() as conn:
        await conn.execute("UPDATE voice_memos SET title = %s WHERE id = %s", (title, memo_id))
    return _row((*row[:3], title, *row[4:]))


@router.delete("/{memo_id}", status_code=204)
async def delete(memo_id: str):
    row = await _get(memo_id)
    _path(memo_id, row[5]).unlink(missing_ok=True)
    async with await store.connect() as conn:
        await conn.execute("DELETE FROM voice_memos WHERE id = %s", (memo_id,))
    return Response(status_code=204)


ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
<rect width="512" height="512" rx="112" fill="#16181d"/>
<circle cx="256" cy="256" r="168" fill="#e0685a"/>
<rect x="216" y="136" width="80" height="150" rx="40" fill="#fff"/>
<path d="M172 250a84 84 0 0 0 168 0M256 334v44" fill="none" stroke="#fff" stroke-width="24" stroke-linecap="round"/>
</svg>"""

MANIFEST = """{
  "name": "Journal vocal",
  "short_name": "Journal vocal",
  "lang": "fr",
  "start_url": "app",
  "scope": "./",
  "display": "standalone",
  "background_color": "#16181d",
  "theme_color": "#16181d",
  "icons": [{ "src": "icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable" }],
  "shortcuts": [{ "name": "Enregistrer", "url": "app?go=1" }]
}"""

APP_HTML = (Path(__file__).parent / "memos_app.html").read_text(encoding="utf-8")
