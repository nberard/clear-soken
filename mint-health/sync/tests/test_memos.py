"""Tests du journal vocal.

Unitaires : toujours. API complète (vraie base) : seulement si TEST_DATABASE_URL est défini,
par ex. postgresql://health:health@localhost:5432/health
"""
import os
import tempfile
from datetime import datetime, timezone

import pytest

os.environ.setdefault("TZ", "Europe/Paris")
os.environ.setdefault("MEMO_DIR", tempfile.mkdtemp(prefix="memos-"))
if os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

from healthsync import memos  # noqa: E402

needs_db = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL non défini")


def test_default_title_in_local_time():
    # 8 h 05 UTC le 27/10/2026 = 9 h 05 à Paris (heure d'hiver)
    at = datetime(2026, 10, 27, 8, 5, tzinfo=timezone.utc)
    assert memos.default_title(at) == "Mardi 27 oct. · 09:05"


def test_id_check_blocks_path_traversal():
    with pytest.raises(Exception):
        memos._check_id("../../etc/passwd")
    memos._check_id("20261027-090500-abc123")


def test_base_mime():
    assert memos._base_mime("audio/webm;codecs=opus") == "audio/webm"
    assert memos._base_mime(None) == ""


@needs_db
def test_api_roundtrip():
    from fastapi.testclient import TestClient

    from healthsync.main import app

    audio = b"OggS" + b"\0" * 2000
    with TestClient(app) as c:
        r = c.post("/memos?device=mint&duration=12.5&title=Idée%20vélo", content=audio,
                   headers={"Content-Type": "audio/ogg"})
        assert r.status_code == 201, r.text
        memo = r.json()
        assert memo["device"] == "mint" and memo["duration_s"] == 12.5 and memo["title"] == "Idée vélo"

        assert any(m["id"] == memo["id"] for m in c.get("/memos").json())

        r = c.get(f"/memos/{memo['id']}/audio")
        assert r.status_code == 200 and r.content == audio and r.headers["content-type"] == "audio/ogg"

        assert c.patch(f"/memos/{memo['id']}", json={"title": "Renommé"}).json()["title"] == "Renommé"

        # Refus : mauvais format, appareil inconnu, fichier vide
        assert c.post("/memos", content=b"x", headers={"Content-Type": "text/plain"}).status_code == 415
        assert c.post("/memos?device=tv", content=b"x", headers={"Content-Type": "audio/ogg"}).status_code == 400
        assert c.post("/memos", content=b"", headers={"Content-Type": "audio/ogg"}).status_code == 400

        assert c.get("/memos/app").text.startswith("<!doctype html>")

        assert c.delete(f"/memos/{memo['id']}").status_code == 204
        assert c.get(f"/memos/{memo['id']}/audio").status_code == 404
        assert not any(p.name.startswith(memo["id"]) for p in memos.MEMO_DIR.iterdir())
