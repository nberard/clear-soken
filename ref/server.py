"""Serveur de « Ça me fait penser à… » (ref.touplitoui.me).

Sert la page et une petite API JSON. Les données tiennent dans un seul fichier
(REF_DATA, par défaut /data/refs.json). Le mot de passe est géré par Caddy
(basic_auth) : ce serveur n'est joignable que depuis le réseau Docker « proxy ».

Routes :
  GET    /                    la page
  GET    /api/data            {refs, cats, suggest}
  PUT    /api/refs/<id>       crée ou remplace une référence
  DELETE /api/refs/<id>       supprime une référence
  PUT    /api/categories      {ref, trig, lang}
  POST   /api/suggest         propositions de Claude (si ANTHROPIC_API_KEY est défini)
  GET    /healthz             ok
"""

import json
import os
import re
import tempfile
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
INDEX = HERE / "index.html"
DATA_FILE = Path(os.environ.get("REF_DATA", "/data/refs.json"))
MAX_BODY = 64 * 1024
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
REF_FIELDS = {
    "trigger": 2000, "trigType": 80, "srcLang": 80,
    "refTitle": 300, "refType": 80, "refYear": 200, "refLang": 80,
    "refDetail": 2000, "note": 2000,
}
CAT_KEYS = ("ref", "trig", "lang")
MODEL = os.environ.get("REF_MODEL", "claude-opus-5-5")

_lock = threading.Lock()


# --- stockage ---------------------------------------------------------------

def load_data():
    try:
        with DATA_FILE.open(encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    data.setdefault("refs", {})
    data.setdefault("cats", None)
    return data


def save_data(data):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Écriture atomique : jamais de fichier à moitié écrit si le conteneur s'arrête
    fd, tmp = tempfile.mkstemp(dir=DATA_FILE.parent, prefix=".refs-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, DATA_FILE)


def clean_ref(body):
    if not isinstance(body, dict):
        raise ValueError("objet attendu")
    ref = {}
    for key, limit in REF_FIELDS.items():
        val = body.get(key, "")
        if not isinstance(val, str):
            raise ValueError(f"{key} doit être du texte")
        ref[key] = val.strip()[:limit]
    if not ref["trigger"] or not ref["refTitle"]:
        raise ValueError("trigger et refTitle sont obligatoires")
    for key in ("createdAt", "updatedAt"):
        val = body.get(key)
        ref[key] = int(val) if isinstance(val, (int, float)) else 0
    return ref


def clean_cats(body):
    if not isinstance(body, dict):
        raise ValueError("objet attendu")
    cats = {}
    for key in CAT_KEYS:
        items = body.get(key)
        if not isinstance(items, list) or not items:
            raise ValueError(f"{key} doit être une liste non vide")
        cats[key] = [str(x).strip()[:80] for x in items if str(x).strip()][:100]
    return cats


# --- suggestions (Claude) ---------------------------------------------------

SUGGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "type": {"type": "string"},
                    "year": {"type": "string"},
                    "detail": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["title", "type", "year", "detail", "why"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["candidates"],
    "additionalProperties": False,
}

_client = None


def claude_client():
    global _client
    if _client is None:
        import anthropic  # importé seulement si la clé est configurée

        _client = anthropic.Anthropic()
    return _client


def suggest_enabled():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def suggest(body):
    def txt(key, limit=500):
        val = body.get(key, "")
        return val.strip()[:limit] if isinstance(val, str) else ""

    types = body.get("types") if isinstance(body.get("types"), list) else []
    types = ", ".join(str(t)[:40] for t in types[:30])
    prompt = (
        "Tu aides quelqu'un à retrouver une référence de culture populaire "
        "(film, série, chanson, livre, jeu vidéo, pub, mème…).\n"
        f"Ce qu'on lui a dit (en {txt('srcLang', 40) or '?'}) : \"{txt('said')}\"\n"
        f"Langue de la référence recherchée : {txt('refLang', 40) or '?'} "
        "(peut différer de la phrase dite : pense aux traductions, titres originaux "
        "et jeux de mots entre langues)\n"
        f"Sa description de la référence : \"{txt('clue')}\"\n"
        f"Type qu'il pense : {txt('type', 40)}\n"
        f"Types possibles : {types}\n\n"
        "Propose jusqu'à 5 candidats plausibles, du plus probable au moins probable. "
        "Pour chacun : title (titre original ou le plus connu), type (un des types possibles), "
        "year (année et/ou artiste ou réalisateur), detail (le moment ou la réplique précise, "
        "une phrase), why (pourquoi ça colle, très court). "
        "N'invente pas de titres : si tu n'es pas sûr, dis-le dans why."
    )
    client = claude_client()
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": SUGGEST_SCHEMA},
        },
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        return {"candidates": []}
    text = next((b.text for b in response.content if b.type == "text"), "")
    data = json.loads(text) if text else {"candidates": []}
    data["candidates"] = data.get("candidates", [])[:5]
    return data


# --- HTTP -------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "ref"

    def log_message(self, fmt, *args):  # pas de journal d'accès
        pass

    def send_json(self, status, payload=None):
        body = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Cache-Control", "no-store")
        if payload is not None:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise OverflowError
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            raise ValueError("Content-Type application/json attendu")
        return json.loads(self.rfile.read(length) or b"null")

    def handle_write(self, fn):
        try:
            body = self.read_json()
            fn(body)
        except OverflowError:
            self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "trop long"})
        except (ValueError, json.JSONDecodeError) as e:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(e)})

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = INDEX.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/data":
            with _lock:
                data = load_data()
            refs = [{"id": k, **v} for k, v in data["refs"].items()]
            self.send_json(HTTPStatus.OK, {"refs": refs, "cats": data["cats"], "suggest": suggest_enabled()})
        elif self.path == "/healthz":
            self.send_json(HTTPStatus.OK, {"ok": True})
        else:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "introuvable"})

    def do_PUT(self):
        m = re.fullmatch(r"/api/refs/([^/]+)", self.path)
        if m and ID_RE.match(m.group(1)):
            ref_id = m.group(1)

            def put_ref(body):
                ref = clean_ref(body)
                with _lock:
                    data = load_data()
                    data["refs"][ref_id] = ref
                    save_data(data)
                self.send_json(HTTPStatus.NO_CONTENT)

            self.handle_write(put_ref)
        elif self.path == "/api/categories":

            def put_cats(body):
                cats = clean_cats(body)
                with _lock:
                    data = load_data()
                    data["cats"] = cats
                    save_data(data)
                self.send_json(HTTPStatus.NO_CONTENT)

            self.handle_write(put_cats)
        else:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "introuvable"})

    def do_DELETE(self):
        m = re.fullmatch(r"/api/refs/([^/]+)", self.path)
        if not (m and ID_RE.match(m.group(1))):
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "introuvable"})
            return
        with _lock:
            data = load_data()
            if data["refs"].pop(m.group(1), None) is not None:
                save_data(data)
        self.send_json(HTTPStatus.NO_CONTENT)

    def do_POST(self):
        if self.path != "/api/suggest":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "introuvable"})
            return
        if not suggest_enabled():
            self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "ANTHROPIC_API_KEY absent"})
            return

        def run(body):
            if not isinstance(body, dict):
                raise ValueError("objet attendu")
            import anthropic

            try:
                self.send_json(HTTPStatus.OK, suggest(body))
            except anthropic.RateLimitError:
                self.send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "trop de demandes"})
            except (anthropic.APIStatusError, anthropic.APIConnectionError, json.JSONDecodeError) as e:
                print(f"suggest: {type(e).__name__}: {e}", flush=True)
                self.send_json(HTTPStatus.BAD_GATEWAY, {"error": "Claude indisponible"})

        self.handle_write(run)


def main():
    port = int(os.environ.get("PORT", "8000"))
    print(f"ref sur :{port}, données dans {DATA_FILE}, suggestions {'activées' if suggest_enabled() else 'désactivées'}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
