"""Tests de l'API de ref (sans réseau ni clé Claude) : python3 -m unittest ref/test_server.py"""

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

TMP = tempfile.mkdtemp()
os.environ["REF_DATA"] = str(Path(TMP) / "refs.json")
os.environ.pop("ANTHROPIC_API_KEY", None)

import server  # noqa: E402


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def call(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as r:
                raw = r.read()
                return r.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            return e.code, None

    def test_page(self):
        with urllib.request.urlopen(self.base + "/") as r:
            self.assertIn(b"a me fait penser", r.read())

    def test_cycle(self):
        ref = {"trigger": "Je reviendrai", "trigType": "Phrase", "srcLang": "Français",
               "refTitle": "Terminator", "refType": "Film", "refLang": "Anglais", "createdAt": 1}
        self.assertEqual(self.call("PUT", "/api/refs/abc", ref)[0], 204)
        status, data = self.call("GET", "/api/data")
        self.assertEqual(status, 200)
        self.assertFalse(data["suggest"])
        got = next(r for r in data["refs"] if r["id"] == "abc")
        self.assertEqual(got["refTitle"], "Terminator")
        self.assertEqual(got["refLang"], "Anglais")
        self.assertEqual(self.call("DELETE", "/api/refs/abc")[0], 204)
        self.assertFalse(any(r["id"] == "abc" for r in self.call("GET", "/api/data")[1]["refs"]))

    def test_validation(self):
        self.assertEqual(self.call("PUT", "/api/refs/x", {"trigger": "", "refTitle": "a"})[0], 400)
        self.assertEqual(self.call("PUT", "/api/refs/..%2F", {"trigger": "a", "refTitle": "b"})[0], 404)
        self.assertEqual(self.call("PUT", "/api/categories", {"ref": []})[0], 400)

    def test_categories(self):
        cats = {"ref": ["Film"], "trig": ["Mot"], "lang": ["Français", "Japonais"]}
        self.assertEqual(self.call("PUT", "/api/categories", cats)[0], 204)
        self.assertEqual(self.call("GET", "/api/data")[1]["cats"], cats)

    def test_suggest_off(self):
        self.assertEqual(self.call("POST", "/api/suggest", {"clue": "robot"})[0], 503)


if __name__ == "__main__":
    unittest.main()
