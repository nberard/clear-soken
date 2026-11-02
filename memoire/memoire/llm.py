"""Backends LLM : API (Mistral ou Claude) et local (Ollama).

Tous exposent la même méthode : `completer(system, prompt, json_mode)`.
"""
from __future__ import annotations

import json
import re
import time
from typing import Protocol

import httpx

from .config import Config


class Indisponible(Exception):
    """Le backend ne répond pas (ex. PC éteint pour le modèle local)."""


# Connexion courte : un hôte injoignable doit échouer vite, pas bloquer des minutes.
DELAI_API = httpx.Timeout(120, connect=10)
DELAI_LOCAL = httpx.Timeout(600, connect=5)


class LLM(Protocol):
    nom: str
    local: bool
    max_chars: int  # taille de contexte qu'on s'autorise à envoyer

    def completer(self, system: str, prompt: str, json_mode: bool = False) -> str: ...


class Mistral:
    nom, local, max_chars = "mistral", False, 60_000

    def __init__(self, key: str, model: str):
        self.key, self.model = key, model

    def completer(self, system: str, prompt: str, json_mode: bool = False) -> str:
        corps = {"model": self.model, "temperature": 0.2,
                 "messages": [{"role": "system", "content": system},
                              {"role": "user", "content": prompt}]}
        if json_mode:
            corps["response_format"] = {"type": "json_object"}
        try:
            r = httpx.post("https://api.mistral.ai/v1/chat/completions", json=corps, timeout=DELAI_API,
                           headers={"Authorization": f"Bearer {self.key}"})
            r.raise_for_status()
        except httpx.TransportError as e:
            raise Indisponible(str(e)) from e
        return r.json()["choices"][0]["message"]["content"]


class Anthropic:
    nom, local, max_chars = "anthropic", False, 60_000

    def __init__(self, key: str, model: str):
        self.key, self.model = key, model

    def completer(self, system: str, prompt: str, json_mode: bool = False) -> str:
        if json_mode:
            system += "\nRéponds uniquement avec un objet JSON valide, sans texte autour."
        corps = {"model": self.model, "max_tokens": 2048, "system": system,
                 "messages": [{"role": "user", "content": prompt}]}
        try:
            r = httpx.post("https://api.anthropic.com/v1/messages", json=corps, timeout=DELAI_API,
                           headers={"x-api-key": self.key, "anthropic-version": "2023-06-01"})
            r.raise_for_status()
        except httpx.TransportError as e:
            raise Indisponible(str(e)) from e
        return "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text")


class Ollama:
    # Modèle plus petit : on lui envoie moins de texte.
    nom, local, max_chars = "ollama", True, 16_000

    PAUSE = 60  # après un échec, on ne réessaie pas avant 60 s

    def __init__(self, url: str, model: str):
        self.url, self.model = url.rstrip("/"), model
        self._echec_a: float | None = None

    def completer(self, system: str, prompt: str, json_mode: bool = False) -> str:
        corps = {"model": self.model, "stream": False, "options": {"temperature": 0.2},
                 "messages": [{"role": "system", "content": system},
                              {"role": "user", "content": prompt}]}
        if json_mode:
            corps["format"] = "json"
        if self._echec_a is not None and time.monotonic() - self._echec_a < self.PAUSE:
            raise Indisponible(f"Ollama injoignable ({self.url}), nouvel essai dans moins de {self.PAUSE} s")
        try:
            r = httpx.post(f"{self.url}/api/chat", json=corps, timeout=DELAI_LOCAL)
            r.raise_for_status()
        except httpx.TransportError as e:
            self._echec_a = time.monotonic()
            raise Indisponible(f"Ollama injoignable ({self.url}) : {e}") from e
        return r.json()["message"]["content"]


class CleManquante(Exception):
    """Clé d'API absente : erreur de configuration, pas une panne réseau."""


def construire(cfg: Config, verifier: bool = True) -> tuple[LLM, LLM]:
    """Renvoie (api, local). Lève CleManquante si la clé de l'API choisie est vide.
    Avec MEMOIRE_API=ollama, tout passe par le modèle local : aucune clé, rien ne sort."""
    local = Ollama(cfg.ollama_url, cfg.ollama_model)
    if cfg.api in ("ollama", "local"):
        return local, local
    cle, var = ((cfg.anthropic_key, "ANTHROPIC_API_KEY") if cfg.api == "anthropic"
                else (cfg.mistral_key, "MISTRAL_API_KEY"))
    if verifier and not cle.strip():
        raise CleManquante(f"{var} est vide : renseigne-la dans memoire/.env puis relance "
                           "« make memoire-deploy » pour que le conteneur la prenne en compte.")
    if cfg.api == "anthropic":
        api: LLM = Anthropic(cfg.anthropic_key, cfg.anthropic_model)
    else:
        api = Mistral(cfg.mistral_key, cfg.mistral_model)
    return api, local


def extraire_json(texte: str) -> dict:
    """Tolère un JSON entouré de texte ou de ```json (fréquent avec les petits modèles)."""
    try:
        return json.loads(texte)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", texte, re.S)
        if not m:
            raise
        return json.loads(m.group(0))
