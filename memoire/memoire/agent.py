"""L'agent : répond à une question en lisant l'arbre de contexte.

1. Route la question vers une ou plusieurs casquettes (sans appel LLM, donc
   sans rien envoyer : mots-clés + casquettes des passages trouvés).
2. Si une casquette privée est concernée, TOUT se fait avec le modèle local.
3. Charge : racine -> profils des casquettes -> sujets -> passages exacts.
"""
from __future__ import annotations

import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field

from .config import Config
from .llm import LLM, Indisponible
from .sensible import score_casquettes

SYSTEME = ("Tu es l'assistant personnel de l'utilisateur. Tu disposes d'extraits de sa mémoire "
           "(résumés et passages de ses anciennes conversations avec des IA). Réponds en français, "
           "en t'appuyant sur ces extraits ; cite la source entre crochets [source, date] quand tu "
           "utilises un passage. Si la mémoire ne contient pas l'information, dis-le.")


@dataclass
class Reponse:
    texte: str
    casquettes: list[str]
    backend: str
    sources: list[dict] = field(default_factory=list)


def _requete_fts(question: str) -> str:
    mots = [m for m in re.findall(r"\w{3,}", question.lower())]
    return " OR ".join(f'"{m}"' for m in mots[:20])


def rechercher(conn: sqlite3.Connection, question: str, limite: int = 30) -> list[sqlite3.Row]:
    q = _requete_fts(question)
    if not q:
        return []
    return conn.execute(
        """SELECT f.conv_id, f.idx, snippet(messages_fts, 0, '', '', ' … ', 48) AS extrait,
                  c.titre, c.source, c.cree_le, c.sensible,
                  (SELECT casquette FROM conv_casquettes WHERE conv_id = f.conv_id AND principal = 1) AS casquette
           FROM messages_fts f JOIN conversations c ON c.id = f.conv_id
           WHERE messages_fts MATCH ? ORDER BY rank LIMIT ?""", (q, limite)).fetchall()


def router(conn: sqlite3.Connection, cfg: Config, question: str) -> list[str]:
    # Les mots-clés de la question priment ; les passages trouvés départagent seulement
    # (sinon une casquette mal remplie attire toutes les questions).
    scores = Counter({c: 3 * n for c, n in score_casquettes(question, cfg).items()})
    for r in rechercher(conn, question, 20):
        if r["casquette"]:
            scores[r["casquette"]] += 0.25
    if not scores:
        return list(cfg.casquettes)  # rien de clair : on regarde partout
    meilleur = max(scores.values())
    return [c for c, s in scores.most_common() if s >= meilleur / 2]


def demander(conn: sqlite3.Connection, cfg: Config, question: str, api: LLM, local: LLM,
             casquettes: list[str] | None = None) -> Reponse:
    casquettes = [c for c in (casquettes or router(conn, cfg, question)) if c in cfg.casquettes]
    prive = any(c in cfg.privees for c in casquettes)
    llm = local if prive else api
    budget = llm.max_chars
    morceaux: list[str] = []

    def ajouter(txt: str) -> bool:
        nonlocal budget
        if len(txt) > budget:
            return False
        morceaux.append(txt)
        budget -= len(txt)
        return True

    racine = conn.execute("SELECT resume FROM noeuds WHERE id = ?",
                          ("racine:privee" if prive else "racine",)).fetchone()
    if racine and racine["resume"]:
        ajouter(f"# Vue d'ensemble\n{racine['resume']}")

    # Budget partagé : chaque casquette a sa part, aucune n'écrase les autres.
    part = budget // (2 * max(len(casquettes), 1))
    for c in casquettes:
        reste = part
        for n in conn.execute("SELECT niveau, titre, resume FROM noeuds WHERE casquette = ? "
                              "AND resume IS NOT NULL ORDER BY niveau = 'casquette' DESC, maj_le DESC", (c,)):
            bloc = f"# {c} — {n['titre']}\n{n['resume']}"
            if len(bloc) > reste or not ajouter(bloc):
                break
            reste -= len(bloc)

    # Passages exacts (feuilles), filtrés selon la confidentialité.
    sources = []
    for r in rechercher(conn, question):
        if r["sensible"] and not llm.local:
            continue  # un passage sensible ne part jamais à l'API
        if r["casquette"] and r["casquette"] not in casquettes:
            lie = conn.execute("SELECT 1 FROM conv_casquettes WHERE conv_id=? AND casquette IN (%s)"
                               % ",".join("?" * len(casquettes)), (r["conv_id"], *casquettes)).fetchone()
            if not lie:
                continue
        date = (r["cree_le"] or "")[:10]
        # Le message suivant (souvent la réponse) donne le sens du passage.
        suite = conn.execute("SELECT role, contenu FROM messages WHERE conv_id=? AND idx=?",
                             (r["conv_id"], r["idx"] + 1)).fetchone()
        texte = f"[{r['source']}, {date}] « {r['titre']} » : {r['extrait']}"
        if suite:
            texte += f"\n  → [{suite['role']}] {suite['contenu'][:800]}"
        if not ajouter(texte):
            break
        sources.append({"conv_id": r["conv_id"], "titre": r["titre"], "source": r["source"], "date": date})

    contexte = "\n\n".join(morceaux) or "(mémoire vide pour l'instant)"
    try:
        texte = llm.completer(SYSTEME, f"Mémoire :\n{contexte}\n\nQuestion : {question}")
    except Indisponible as e:
        privees = [c for c in casquettes if c in cfg.privees]
        motif = f"Cette question touche une casquette privée ({', '.join(privees)}) et le" if privees else "Le"
        texte = (f"{motif} modèle local (Ollama) ne répond pas : vérifie que ton PC est allumé "
                 f"et que le tunnel est ouvert, puis réessaie.\n({e})")
    return Reponse(texte.strip(), casquettes, llm.nom, sources)
