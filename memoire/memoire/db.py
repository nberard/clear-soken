"""Stockage SQLite (léger : le serveur n'a que 4 Go de RAM).

L'arbre de contexte :
  racine            vue globale (casquettes non privées)  -> traitée par l'API
  racine:privee     vue transverse (toutes casquettes)     -> traitée en local
  casquette:<nom>   profil d'une casquette
  sujet:<nom>:<x>   résumé d'un sujet dans une casquette
  conversations     les feuilles (résumé + messages bruts)

Une conversation a UNE casquette principale (sa place dans l'arbre) et des
liens vers d'autres casquettes (table conv_casquettes, principal = 0).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,          -- <source>:<id d'origine>
    source      TEXT NOT NULL,             -- chatgpt, claude, gemini, mistral
    titre       TEXT,
    cree_le     TEXT,
    maj_le      TEXT,
    empreinte   TEXT,                      -- hash du texte, pour les ré-imports
    statut      TEXT NOT NULL DEFAULT 'nouveau',  -- nouveau, en_attente_local, traite, erreur
    sensible    INTEGER NOT NULL DEFAULT 0,
    sujet       TEXT,
    resume      TEXT,
    erreur      TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    conv_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    idx     INTEGER NOT NULL,
    role    TEXT NOT NULL,
    contenu TEXT NOT NULL,
    cree_le TEXT,
    PRIMARY KEY (conv_id, idx)
);
CREATE TABLE IF NOT EXISTS conv_casquettes (
    conv_id    TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    casquette  TEXT NOT NULL,
    principal  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (conv_id, casquette)
);
CREATE TABLE IF NOT EXISTS noeuds (
    id         TEXT PRIMARY KEY,
    niveau     TEXT NOT NULL,              -- racine, casquette, sujet
    casquette  TEXT,
    titre      TEXT,
    resume     TEXT,
    a_refaire  INTEGER NOT NULL DEFAULT 1,
    maj_le     TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    contenu, conv_id UNINDEXED, idx UNINDEXED, tokenize = 'unicode61 remove_diacritics 2'
);
CREATE INDEX IF NOT EXISTS idx_conv_statut ON conversations(statut);
CREATE INDEX IF NOT EXISTS idx_cc_casquette ON conv_casquettes(casquette);
"""


def connecter(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    return conn


def texte_conversation(conn: sqlite3.Connection, conv_id: str) -> str:
    rows = conn.execute(
        "SELECT role, contenu FROM messages WHERE conv_id = ? ORDER BY idx", (conv_id,)
    ).fetchall()
    return "\n\n".join(f"[{r['role']}] {r['contenu']}" for r in rows)
