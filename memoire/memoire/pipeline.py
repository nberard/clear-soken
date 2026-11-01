"""Traitement : classe et résume chaque conversation, puis reconstruit l'arbre.

Règle de confidentialité (hybride) :
- une conversation repérée sensible est traitée UNIQUEMENT par le modèle local ;
- un nœud de l'arbre d'une casquette privée est résumé UNIQUEMENT en local ;
- si le modèle local est injoignable, le travail attend (statut en_attente_local).
"""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from datetime import datetime, timezone

from .config import Config
from .db import texte_conversation
from .llm import LLM, Indisponible, extraire_json
from .sensible import est_sensible

SYSTEME = ("Tu organises la mémoire personnelle de l'utilisateur à partir de ses conversations "
           "avec des assistants IA. Tu écris en français, de façon factuelle et concise, "
           "à la deuxième personne (« tu »).")

MAX_ENFANTS = 40  # résumés enfants lus pour refaire un nœud


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60] or "divers"


def _tronquer(texte: str, max_chars: int) -> str:
    """Garde le début et la fin : c'est là que sont le sujet et les conclusions."""
    if len(texte) <= max_chars:
        return texte
    moitie = max_chars // 2
    return texte[:moitie] + "\n\n[…conversation tronquée…]\n\n" + texte[-moitie:]


def _prompt_conversation(cfg: Config, titre: str, texte: str) -> str:
    liste = "\n".join(f"- {n} : {c.description}" for n, c in cfg.casquettes.items())
    return f"""Casquettes possibles :
{liste}

Conversation « {titre} » :
<<<
{texte}
>>>

Réponds avec un objet JSON :
{{"casquette": "<la casquette principale>",
  "autres_casquettes": ["<autres casquettes réellement concernées>"],
  "sujet": "<sujet court, 2 à 5 mots, réutilisable entre conversations>",
  "resume": "<5 lignes max : faits, décisions, ressentis, ce qui reste à faire>"}}"""


def traiter_conversation(conn: sqlite3.Connection, cfg: Config, conv_id: str,
                         api: LLM, local: LLM) -> str:
    conv = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
    texte = texte_conversation(conn, conv_id)
    sensible = bool(conv["sensible"]) or est_sensible(f"{conv['titre']}\n{texte}", cfg)
    llm = local if sensible else api

    try:
        brut = llm.completer(SYSTEME, _prompt_conversation(cfg, conv["titre"], _tronquer(texte, llm.max_chars)),
                             json_mode=True)
        res = extraire_json(brut)
    except Indisponible as e:
        statut = "en_attente_local" if llm.local else "nouveau"  # l'API sera réessayée au prochain passage
        with conn:
            conn.execute("UPDATE conversations SET statut=?, sensible=?, erreur=? WHERE id=?",
                         (statut, int(sensible), str(e)[:500], conv_id))
        return statut if llm.local else "api_injoignable"
    except Exception as e:  # réponse illisible, quota… : on note et on passe
        with conn:
            conn.execute("UPDATE conversations SET statut='erreur', erreur=? WHERE id=?", (str(e)[:500], conv_id))
        return "erreur"

    principale = res.get("casquette") if res.get("casquette") in cfg.casquettes else next(iter(cfg.casquettes))
    autres = {c for c in res.get("autres_casquettes") or [] if c in cfg.casquettes} - {principale}
    # Une API qui découvre après coup une casquette privée : on marque sensible pour la suite.
    sensible = sensible or principale in cfg.privees or bool(autres & cfg.privees)
    # Une conversation sensible est rangée sous une casquette privée : les nœuds des
    # casquettes non privées sont résumés par l'API et ne doivent jamais la contenir.
    # Sa casquette d'origine reste un lien (visible depuis le local).
    if sensible and principale not in cfg.privees:
        privee = next((a for a in autres if a in cfg.privees), None) or sorted(cfg.privees)[0]
        autres = (autres | {principale}) - {privee}
        principale = privee
    sujet = (res.get("sujet") or "divers").strip()[:80]

    with conn:
        anciens = conn.execute("SELECT casquette FROM conv_casquettes WHERE conv_id=? AND principal=1",
                               (conv_id,)).fetchall()
        ancien_sujet = conv["sujet"]
        conn.execute("DELETE FROM conv_casquettes WHERE conv_id = ?", (conv_id,))
        conn.execute("INSERT INTO conv_casquettes VALUES (?, ?, 1)", (conv_id, principale))
        conn.executemany("INSERT INTO conv_casquettes VALUES (?, ?, 0)", [(conv_id, a) for a in autres])
        conn.execute(
            "UPDATE conversations SET statut='traite', sensible=?, sujet=?, resume=?, erreur=NULL WHERE id=?",
            (int(sensible), sujet, str(res.get("resume") or "").strip(), conv_id))
        # Marque à refaire les branches touchées (l'ancienne et la nouvelle).
        for a in anciens:
            if ancien_sujet:
                _marquer(conn, a["casquette"], ancien_sujet)
        _marquer(conn, principale, sujet)
    return "traite"


def _marquer(conn: sqlite3.Connection, casquette: str, sujet: str) -> None:
    nid = f"sujet:{casquette}:{_slug(sujet)}"
    conn.execute(
        "INSERT INTO noeuds (id, niveau, casquette, titre, a_refaire) VALUES (?, 'sujet', ?, ?, 1) "
        "ON CONFLICT(id) DO UPDATE SET a_refaire = 1", (nid, casquette, sujet))
    conn.execute(
        "INSERT INTO noeuds (id, niveau, casquette, titre, a_refaire) VALUES (?, 'casquette', ?, ?, 1) "
        "ON CONFLICT(id) DO UPDATE SET a_refaire = 1", (f"casquette:{casquette}", casquette, casquette))
    for rid in ("racine", "racine:privee"):
        conn.execute(
            "INSERT INTO noeuds (id, niveau, titre, a_refaire) VALUES (?, 'racine', ?, 1) "
            "ON CONFLICT(id) DO UPDATE SET a_refaire = 1", (rid, rid))


def _resumer(llm: LLM, consigne: str, enfants: list[str]) -> str:
    corps = _tronquer("\n\n---\n\n".join(enfants), llm.max_chars)
    return llm.completer(SYSTEME, f"{consigne}\n\n<<<\n{corps}\n>>>").strip()


def reconstruire_arbre(conn: sqlite3.Connection, cfg: Config, api: LLM, local: LLM) -> dict[str, int]:
    """Refait les nœuds marqués, du bas (sujets) vers le haut (racines)."""
    stats = {"refaits": 0, "en_attente_local": 0}

    def llm_pour(casquette: str | None) -> LLM:
        return local if casquette in cfg.privees else api

    def refaire(nid: str, llm: LLM, consigne: str, enfants: list[str]) -> None:
        if not enfants:
            with conn:
                conn.execute("DELETE FROM noeuds WHERE id = ?", (nid,))
            return
        try:
            resume = _resumer(llm, consigne, enfants)
        except Indisponible:
            stats["en_attente_local"] += 1
            return
        with conn:
            conn.execute("UPDATE noeuds SET resume=?, a_refaire=0, maj_le=? WHERE id=?",
                         (resume, _maintenant(), nid))
        stats["refaits"] += 1

    # 1. Sujets : à partir des résumés de conversations (casquette principale).
    for n in conn.execute("SELECT * FROM noeuds WHERE niveau='sujet' AND a_refaire=1").fetchall():
        rows = conn.execute(
            """SELECT c.titre, c.cree_le, c.resume, c.sujet FROM conversations c
               JOIN conv_casquettes cc ON cc.conv_id = c.id AND cc.principal = 1
               WHERE cc.casquette = ? AND c.statut = 'traite'
               ORDER BY c.cree_le DESC""", (n["casquette"],)).fetchall()
        enfants = [f"{r['cree_le'] or ''} — {r['titre']}\n{r['resume']}"
                   for r in rows if _slug(r["sujet"] or "") == n["id"].split(":", 2)[2]][:MAX_ENFANTS]
        refaire(n["id"], llm_pour(n["casquette"]),
                f"Résume le sujet « {n['titre']} » à partir de ces conversations (plus récentes d'abord) : "
                "où tu en es, ce qui a été décidé, ce qui reste ouvert. 10 lignes max.", enfants)

    # 2. Casquettes : à partir des sujets.
    for n in conn.execute("SELECT * FROM noeuds WHERE niveau='casquette' AND a_refaire=1").fetchall():
        rows = conn.execute("SELECT titre, resume FROM noeuds WHERE niveau='sujet' AND casquette=? "
                            "AND resume IS NOT NULL ORDER BY maj_le DESC", (n["casquette"],)).fetchall()
        desc = cfg.casquettes[n["casquette"]].description if n["casquette"] in cfg.casquettes else ""
        refaire(n["id"], llm_pour(n["casquette"]),
                f"Fais le profil de la casquette « {n['casquette']} » ({desc}) à partir de ses sujets : "
                "situation actuelle, sujets en cours, tendances. 15 lignes max.",
                [f"## {r['titre']}\n{r['resume']}" for r in rows][:MAX_ENFANTS])

    # 3. Racines. « racine » ne voit jamais les casquettes privées (elle part à l'API).
    def profils(inclure_privees: bool) -> list[str]:
        rows = conn.execute("SELECT casquette, resume FROM noeuds WHERE niveau='casquette' "
                            "AND resume IS NOT NULL").fetchall()
        return [f"## {r['casquette']}\n{r['resume']}" for r in rows
                if inclure_privees or r["casquette"] not in cfg.privees]

    racines = {r["id"] for r in conn.execute("SELECT id FROM noeuds WHERE niveau='racine' AND a_refaire=1")}
    if "racine" in racines:
        refaire("racine", api, "Fais une vue d'ensemble très courte (8 lignes max) de la vie de "
                "l'utilisateur à partir de ces profils.", profils(False))
    if "racine:privee" in racines:
        refaire("racine:privee", local, "Fais une vue transverse (12 lignes max) à partir de ces profils : "
                "ce qui se passe dans chaque domaine et surtout les liens entre domaines "
                "(ex. travail et humeur, sommeil et stress).", profils(True))
    return stats


def traiter_tout(conn: sqlite3.Connection, cfg: Config, api: LLM, local: LLM,
                 limite: int | None = None, progression=None) -> dict[str, int]:
    ids = [r["id"] for r in conn.execute(
        "SELECT id FROM conversations WHERE statut IN ('nouveau', 'en_attente_local', 'erreur') ORDER BY cree_le")]
    if limite:
        ids = ids[:limite]
    stats: dict[str, int] = {}
    for i, cid in enumerate(ids, 1):
        s = traiter_conversation(conn, cfg, cid, api, local)
        stats[s] = stats.get(s, 0) + 1
        if progression:
            progression(i, len(ids), cid, s)
    arbre = reconstruire_arbre(conn, cfg, api, local)
    stats["noeuds_refaits"] = arbre["refaits"]
    stats["noeuds_en_attente_local"] = arbre["en_attente_local"]
    return stats
