"""Repérage des contenus sensibles AVANT tout envoi à une API.

Volontairement large : mieux vaut traiter en local une conversation pro qui parle
de stress que d'envoyer à une API une conversation de santé mentale.
"""
from __future__ import annotations

import re
import unicodedata

from .config import Config


def _normaliser(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def score_casquettes(texte: str, cfg: Config) -> dict[str, int]:
    """Nombre de mots-clés de chaque casquette présents dans le texte."""
    t = _normaliser(texte)
    scores = {}
    for nom, c in cfg.casquettes.items():
        n = sum(1 for m in c.mots_cles if re.search(rf"\b{re.escape(_normaliser(m))}\b", t))
        if n:
            scores[nom] = n
    return scores


def est_sensible(texte: str, cfg: Config) -> bool:
    scores = score_casquettes(texte, cfg)
    return any(nom in cfg.privees for nom in scores)
