"""Variables communes à tous les tests, fixées avant le premier import de healthsync.config
(qui les lit une seule fois)."""
import os
import tempfile

os.environ.setdefault("TZ", "Europe/Paris")
os.environ.setdefault("CONSO_BOUTIQUES", "boutique-exemple.fr,autre-exemple.fr:cbd")
os.environ.setdefault("HC_INGEST_TOKEN", "secret-test")
os.environ.setdefault("CONSO_INGEST_TOKEN", "jeton-de-test")
os.environ.setdefault("VAPID_FILE", os.path.join(tempfile.mkdtemp(prefix="vapid-"), "vapid.json"))
os.environ.setdefault("MEMO_DIR", tempfile.mkdtemp(prefix="memos-"))
if os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
