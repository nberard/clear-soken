"""API locale : connexion Google, statut pour l'applet, déclenchement de synchro."""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from html import escape

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from . import config, oauth, store, sync

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    for attempt in range(30):  # attendre que Postgres soit prêt
        try:
            await store.init()
            break
        except Exception:
            await asyncio.sleep(2)
    task = asyncio.create_task(sync.loop())
    yield
    task.cancel()


app = FastAPI(title="Mint Health Sync", lifespan=lifespan)


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html><html lang="fr"><meta charset="utf-8">
<title>{escape(title)}</title>
<style>body{{font:16px system-ui;background:#16181d;color:#e6e6e6;display:grid;
place-items:center;height:100vh;margin:0}}main{{max-width:28rem;text-align:center}}
a{{color:#8ab4f8}}</style><main><h1>{escape(title)}</h1>{body}</main></html>"""
    )


@app.get("/auth/start")
async def auth_start():
    try:
        return RedirectResponse(oauth.build_auth_url())
    except RuntimeError as e:
        return _page("Configuration incomplète", f"<p>{escape(str(e))}</p>")


@app.get("/auth/callback")
async def auth_callback(code: str | None = None, state: str = "", error: str | None = None):
    if error or not code:
        return _page("Connexion annulée", f"<p>{escape(error or 'Aucun code reçu')}</p>")
    try:
        await oauth.exchange_code(code, state)
    except Exception as e:
        return _page("Échec de la connexion", f"<p>{escape(str(e))}</p>")
    asyncio.create_task(sync.run_sync(full=True))
    return _page(
        "Google Health connecté ✓",
        "<p>La première synchronisation démarre. Tu peux fermer cet onglet.</p>",
    )


@app.post("/auth/logout")
async def auth_logout():
    await oauth.revoke()
    return {"connected": False}


@app.post("/sync")
async def trigger_sync(full: bool = Query(False)):
    asyncio.create_task(sync.run_sync(full=full))
    return {"started": True, "full": full}


@app.get("/status")
async def status():
    token = oauth.load_token()
    today = datetime.now(config.TZ).date()
    data = {"connected": bool(token and token.get("refresh_token")), "date": today.isoformat()}
    try:
        data.update(await store.summary(today))
    except Exception as e:
        data["db_error"] = str(e)
    return data


@app.get("/healthz")
async def healthz():
    return {"ok": True}
