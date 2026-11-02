"""Import des exports ChatGPT, Claude, Gemini (Takeout) et Mistral (Le Chat).

Chaque lecteur renvoie des `Conv` normalisées. Le format est détecté tout seul ;
on accepte un fichier .json ou le .zip de l'export tel quel.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


@dataclass
class Msg:
    role: str  # user / assistant
    contenu: str
    cree_le: str | None = None


@dataclass
class Conv:
    source: str
    ext_id: str
    titre: str
    cree_le: str | None
    maj_le: str | None
    messages: list[Msg] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"{self.source}:{self.ext_id}"

    @property
    def empreinte(self) -> str:
        h = hashlib.sha256()
        for m in self.messages:
            h.update(f"{m.role}\x00{m.contenu}\x01".encode())
        return h.hexdigest()


def _date(v: Any) -> str | None:
    """Timestamp Unix ou chaîne ISO -> ISO 8601 UTC."""
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, tz=timezone.utc).isoformat(timespec="seconds")
    return str(v)


def _role(r: str | None) -> str:
    r = (r or "").lower()
    return "user" if r in ("user", "human", "utilisateur") else "assistant"


# --- ChatGPT : conversations.json -------------------------------------------

def _est_chatgpt(d: Any) -> bool:
    return isinstance(d, list) and bool(d) and isinstance(d[0], dict) and "mapping" in d[0]


def lire_chatgpt(d: list[dict]) -> Iterable[Conv]:
    for c in d:
        mapping = c.get("mapping") or {}
        # On suit la branche affichée (current_node -> racine), pas les brouillons.
        chemin, noeud = [], c.get("current_node")
        while noeud and noeud in mapping:
            chemin.append(mapping[noeud])
            noeud = mapping[noeud].get("parent")
        msgs = []
        for n in reversed(chemin):
            m = n.get("message") or {}
            role = (m.get("author") or {}).get("role")
            if role not in ("user", "assistant"):
                continue  # system, tool…
            parts = (m.get("content") or {}).get("parts") or []
            texte = "\n".join(p for p in parts if isinstance(p, str)).strip()
            if texte:
                msgs.append(Msg(role, texte, _date(m.get("create_time"))))
        if msgs:
            yield Conv("chatgpt", str(c.get("conversation_id") or c.get("id")),
                       c.get("title") or "Sans titre", _date(c.get("create_time")),
                       _date(c.get("update_time")), msgs)


# --- Claude : conversations.json --------------------------------------------

def _est_claude(d: Any) -> bool:
    return isinstance(d, list) and bool(d) and isinstance(d[0], dict) and "chat_messages" in d[0]


def lire_claude(d: list[dict]) -> Iterable[Conv]:
    for c in d:
        msgs = []
        for m in c.get("chat_messages") or []:
            texte = m.get("text") or ""
            if not texte:
                texte = "\n".join(b.get("text", "") for b in m.get("content") or []
                                  if isinstance(b, dict) and b.get("type") == "text")
            if texte.strip():
                msgs.append(Msg(_role(m.get("sender")), texte.strip(), _date(m.get("created_at"))))
        if msgs:
            yield Conv("claude", str(c.get("uuid")), c.get("name") or "Sans titre",
                       _date(c.get("created_at")), _date(c.get("updated_at")), msgs)


# --- Gemini : Takeout « Mon activité > Applications Gemini » (format JSON) ---
# Chaque entrée = une question + une réponse, sans notion de conversation :
# on regroupe par jour.

def _est_gemini(d: Any) -> bool:
    return (isinstance(d, list) and bool(d) and isinstance(d[0], dict)
            and "header" in d[0] and "time" in d[0]
            and "gemini" in str(d[0].get("header", "")).lower())


def _sans_html(s: str) -> str:
    s = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>", "\n", s, flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def lire_gemini(d: list[dict]) -> Iterable[Conv]:
    jours: dict[str, list[dict]] = {}
    for e in d:
        jours.setdefault(str(e.get("time", ""))[:10], []).append(e)
    for jour, entrees in sorted(jours.items()):
        msgs = []
        for e in sorted(entrees, key=lambda x: x.get("time", "")):
            q = re.sub(r"^(Prompted|Requête envoyée|A demandé)\s*:?\s*", "", e.get("title", "")).strip()
            if q:
                msgs.append(Msg("user", q, e.get("time")))
            rep = "\n".join(_sans_html(i.get("html", "")) for i in e.get("safeHtmlItem") or [])
            if rep:
                msgs.append(Msg("assistant", rep, e.get("time")))
        if msgs:
            yield Conv("gemini", jour, f"Gemini du {jour}", entrees[0].get("time"),
                       entrees[-1].get("time"), msgs)


# --- Mistral Le Chat / format générique ---------------------------------------
# Le format d'export de Le Chat évolue : on accepte toute liste de conversations
# portant une liste « messages » de {role, content|text}. À ajuster sur un vrai export.

def _est_generique(d: Any) -> bool:
    if isinstance(d, dict):
        d = d.get("conversations") or d.get("chats")
    return isinstance(d, list) and bool(d) and isinstance(d[0], dict) and "messages" in d[0]


def lire_generique(d: Any, source: str = "mistral") -> Iterable[Conv]:
    if isinstance(d, dict):
        d = d.get("conversations") or d.get("chats")
    for i, c in enumerate(d):
        msgs = []
        for m in c.get("messages") or []:
            texte = m.get("content") or m.get("text") or ""
            if isinstance(texte, list):  # blocs [{type, text}]
                texte = "\n".join(b.get("text", "") for b in texte if isinstance(b, dict))
            if str(texte).strip():
                msgs.append(Msg(_role(m.get("role") or m.get("sender")), str(texte).strip(),
                                _date(m.get("created_at") or m.get("createdAt"))))
        if msgs:
            yield Conv(source, str(c.get("id") or c.get("uuid") or i),
                       c.get("title") or c.get("name") or "Sans titre",
                       _date(c.get("created_at") or c.get("createdAt")),
                       _date(c.get("updated_at") or c.get("updatedAt")), msgs)


# --- Claude : mémoires et projets (export claude.ai en plusieurs zips) --------
# memories-000.zip : {"memory_files": [{path, content, updated_at}]}
# projects-000.zip : un fichier par projet {uuid, name, description, prompt_template}
# Chacun devient une « conversation » d'un seul message, classée comme les autres.

def _est_memoire_claude(d: Any) -> bool:
    return isinstance(d, dict) and isinstance(d.get("memory_files"), list)


def lire_memoire_claude(d: dict) -> Iterable[Conv]:
    for f in d["memory_files"]:
        contenu = str(f.get("content") or "").strip()
        if contenu:
            chemin = str(f.get("path") or "memoire")
            date = _date(f.get("updated_at"))
            yield Conv("claude_memoire", chemin, f"Mémoire Claude : {chemin}", date, date,
                       [Msg("user", contenu, date)])


def _est_projet_claude(d: Any) -> bool:
    return isinstance(d, dict) and "prompt_template" in d and "uuid" in d


def lire_projet_claude(d: dict) -> Iterable[Conv]:
    morceaux = [str(d.get(k) or "").strip() for k in ("description", "prompt_template")]
    contenu = "\n\n".join(m for m in morceaux if m)
    if contenu:
        yield Conv("claude_projet", str(d["uuid"]), f"Projet Claude : {d.get('name') or 'sans nom'}",
                   _date(d.get("created_at")), _date(d.get("updated_at")),
                   [Msg("user", contenu, _date(d.get("updated_at")))])


# --- Détection et lecture de fichiers ----------------------------------------

def lire_donnees(d: Any, source: str | None = None) -> list[Conv]:
    if source in (None, "chatgpt") and _est_chatgpt(d):
        return list(lire_chatgpt(d))
    if source in (None, "claude") and _est_claude(d):
        return list(lire_claude(d))
    if source in (None, "claude") and _est_memoire_claude(d):
        return list(lire_memoire_claude(d))
    if source in (None, "claude") and _est_projet_claude(d):
        return list(lire_projet_claude(d))
    if source in (None, "gemini") and _est_gemini(d):
        return list(lire_gemini(d))
    if _est_generique(d):
        return list(lire_generique(d, source or "mistral"))
    return []


def lire_fichier(path: str | Path, source: str | None = None) -> list[Conv]:
    path = Path(path)
    if path.suffix.lower() == ".zip":
        convs: list[Conv] = []
        with zipfile.ZipFile(path) as z:
            for nom in z.namelist():
                if nom.lower().endswith(".json"):
                    try:
                        convs += lire_donnees(json.loads(z.read(nom)), source)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
        return convs
    return lire_donnees(json.loads(path.read_text(encoding="utf-8")), source)


def enregistrer(conn: sqlite3.Connection, convs: list[Conv]) -> dict[str, int]:
    """Insère les conversations. Une conversation modifiée depuis le dernier import
    est remise à « nouveau » pour être re-résumée."""
    stats = {"nouvelles": 0, "modifiees": 0, "inchangees": 0}
    with conn:
        for c in convs:
            ancienne = conn.execute("SELECT empreinte FROM conversations WHERE id = ?", (c.id,)).fetchone()
            if ancienne and ancienne["empreinte"] == c.empreinte:
                stats["inchangees"] += 1
                continue
            if ancienne:
                conn.execute("DELETE FROM messages WHERE conv_id = ?", (c.id,))
                conn.execute("DELETE FROM messages_fts WHERE conv_id = ?", (c.id,))
                conn.execute(
                    "UPDATE conversations SET titre=?, maj_le=?, empreinte=?, statut='nouveau' WHERE id=?",
                    (c.titre, c.maj_le, c.empreinte, c.id))
                stats["modifiees"] += 1
            else:
                conn.execute(
                    "INSERT INTO conversations (id, source, titre, cree_le, maj_le, empreinte) VALUES (?,?,?,?,?,?)",
                    (c.id, c.source, c.titre, c.cree_le, c.maj_le, c.empreinte))
                stats["nouvelles"] += 1
            conn.executemany(
                "INSERT INTO messages (conv_id, idx, role, contenu, cree_le) VALUES (?,?,?,?,?)",
                [(c.id, i, m.role, m.contenu, m.cree_le) for i, m in enumerate(c.messages)])
            conn.executemany(
                "INSERT INTO messages_fts (contenu, conv_id, idx) VALUES (?, ?, ?)",
                [(m.contenu, c.id, i) for i, m in enumerate(c.messages)])
    return stats
