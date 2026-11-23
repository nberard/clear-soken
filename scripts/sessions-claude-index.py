#!/usr/bin/env python3
"""Index des sessions Claude Code pour l'espace admin (/admin/sessions/).

Le serveur ne peut pas lire les sessions Claude : c'est une session Claude (la session « observateur ») qui récupère
les événements avec ses outils, les enregistre dans un dossier, puis lance ce script et envoie le résultat :

    python3 scripts/sessions-claude-index.py --sessions sessions.json --pages pages/ \\
        [--precedent index.json] --sortie index.json
    curl -X POST https://clearsoken.touplitoui.me/api/admin/claude/import \\
        -H "Authorization: Bearer $CLAUDE_INDEX_JETON" -H "content-type: application/json" --data-binary @index.json

- sessions.json : la liste des sessions (réponses de list_sessions / get_session, une liste d'objets ou {data: [...]}).
- pages/ : les pages d'événements (réponses brutes de list_events, kinds user), un fichier par page, nommé
  <session_id>__<n>.txt. Le texte autour du JSON (balises ajoutées par l'outil) est ignoré.
- --precedent : index déjà généré ; ses entrées et sorties sont gardées et complétées (mise à jour incrémentale).

Sans dépendance (Python 3.10+). Les secrets évidents (jetons, mots de passe collés) sont masqués.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

TEXTE_MAX = 4000  # caractères gardés par message (les logs collés peuvent être très longs)

STATUTS = {
    "SESSION_STATUS_BUCKET_WORKING": "en cours",
    "SESSION_STATUS_BUCKET_BLOCKED": "attend ma réponse",
    "SESSION_STATUS_BUCKET_REVIEW_READY": "terminée",
    "SESSION_STATUS_BUCKET_COMPLETED": "terminée",
    "SESSION_STATUS_BUCKET_FAILED": "en échec",
}

EXTENSIONS = {
    "image": ("png", "jpg", "jpeg", "gif", "webp", "heic", "svg"),
    "son": ("mp3", "m4a", "wav", "ogg", "flac", "aac", "opus"),
    "video": ("mp4", "mov", "webm", "mkv", "avi"),
    "document": ("pdf", "zip", "csv", "xlsx", "docx", "json", "txt", "md"),
}
TYPE_PAR_EXT = {e: t for t, exts in EXTENSIONS.items() for e in exts}
FICHIER_CITE = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)*[\w][\w .()-]{0,80}\.(%s))\b" % "|".join(TYPE_PAR_EXT), re.I)

SECRETS = [
    re.compile(r"\b(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[abpr]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,})"),
    re.compile(r"(?i)((?:password|passwd|mot de passe|mdp|token|jeton|secret|api[_-]?key|IG_PASSWORD)\s*[:=]\s*)(\S+)"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
]
PR = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+")


def masquer(texte: str) -> str:
    texte = SECRETS[0].sub("[masqué]", texte)
    texte = SECRETS[1].sub(lambda m: m.group(1) + "[masqué]", texte)
    return SECRETS[2].sub("[clé privée masquée]", texte)


def type_de(nom: str, media_type: str = "") -> str:
    if media_type.startswith("image/"):
        return "image"
    if media_type.startswith("audio/"):
        return "son"
    if media_type.startswith("video/"):
        return "video"
    ext = nom.rsplit(".", 1)[-1].lower() if "." in nom else ""
    return TYPE_PAR_EXT.get(ext, "document" if media_type else "autre")


def lire_json(texte: str):
    """Le premier objet JSON qui commence par {"ccr" (réponse de l'outil), sinon le premier objet ou tableau."""
    dec = json.JSONDecoder()
    for debut in [texte.find('{"ccr"'), texte.find("{"), texte.find("[")]:
        if debut >= 0:
            try:
                return dec.raw_decode(texte[debut:])[0]
            except json.JSONDecodeError:
                continue
    raise ValueError("pas de JSON")


def sessions_de(chemin: Path) -> list[dict]:
    v = lire_json(chemin.read_text())
    v = v.get("ccr", v) if isinstance(v, dict) else v
    if isinstance(v, dict):
        v = v.get("data", v.get("sessions", [v]))
    return [s.get("ccr", s) for s in v]


def evenements(dossier: Path, session_id: str) -> list[dict]:
    vus, evts = set(), []
    for f in sorted(dossier.glob(f"{session_id}__*")):
        try:
            data = lire_json(f.read_text()).get("ccr", {}).get("data", [])
        except (ValueError, AttributeError) as e:
            print(f"  {f.name} ignoré : {e}", file=sys.stderr)
            continue
        for e in data:
            u = (e.get("user") or {}).get("uuid")
            if u and u not in vus:
                vus.add(u)
                evts.append(e)
    return sorted(evts, key=lambda e: e.get("created_at", ""))


def analyser(evts: list[dict]) -> tuple[list[dict], dict, set[str]]:
    entrees, branches = [], set()
    sorties = {"prs": {}, "fichiers": [], "commits": []}
    for e in evts:
        cat = (e.get("user") or {}).get("internal_anthropic_catchall") or {}
        msg = cat.get("message") or {}
        contenu = msg.get("content")
        humain = "client_platform" in cat and not e["user"].get("isSynthetic")
        if humain:
            textes, pieces = [], []
            blocs = [{"type": "text", "text": contenu}] if isinstance(contenu, str) else (contenu or [])
            for b in blocs:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text":
                    textes.append(b.get("text") or "")
                elif b.get("type") in ("image", "document"):
                    mt = (b.get("source") or {}).get("media_type", "")
                    pieces.append({"nom": b.get("title") or f"{b['type']} ({mt or 'jointe'})", "type": type_de("", mt) if mt else b["type"]})
            # Fichiers envoyés depuis l'appli (photos, audio, vidéos, documents) : nom et type seulement
            for fa in cat.get("file_attachments") or []:
                nom = fa.get("file_name") or "fichier"
                mt = fa.get("mime_type") or ("image/" if fa.get("is_image") else "")
                pieces.append({"nom": nom, "type": type_de(nom, mt)})
            texte = "\n".join(textes).strip()
            if texte.startswith("<") and ("command-name>" in texte[:200] or "system-reminder" in texte[:200]):
                continue  # messages techniques de l'interface, pas les miens
            for m in FICHIER_CITE.finditer(texte):
                nom = m.group(1).strip()
                if not nom.startswith(("http", "www.")) and all(p["nom"] != nom for p in pieces):
                    pieces.append({"nom": nom, "type": type_de(nom)})
            if texte or pieces:
                entrees.append({"le": e["created_at"], "texte": masquer(texte[:TEXTE_MAX]), "pieces": pieces[:20]})
            continue
        # Résultats d'outils : PR créées, fichiers envoyés, branches poussées
        res = cat.get("tool_use_result")
        brut = json.dumps(res, ensure_ascii=False) if res is not None else ""
        if '"url"' in brut or "pull/" in brut:
            for url in PR.findall(brut):
                sorties["prs"].setdefault(url, {"url": url, "titre": None})
        if isinstance(res, dict):
            for a in res.get("attachments") or []:
                nom = Path(a.get("path") or "fichier").name
                sorties["fichiers"].append({"nom": nom, "legende": masquer((res.get("caption") or "")[:300]) or None})
            push = (res.get("gitOperation") or {}).get("push") or {}
            if push.get("branch"):
                branches.add(push["branch"])
    sorties["prs"] = list(sorties["prs"].values())
    return entrees, sorties, branches


def fusionner(ancien: dict | None, nouveau: dict) -> dict:
    if not ancien:
        return nouveau
    deja = {(e["le"], e["texte"][:80]) for e in ancien.get("entrees", [])}
    nouveau["entrees"] = ancien.get("entrees", []) + [e for e in nouveau["entrees"] if (e["le"], e["texte"][:80]) not in deja]
    vieilles = ancien.get("sorties", {})
    for cle, id_ in (("prs", "url"), ("artifacts", "url"), ("commits", "sha")):
        connus = {x[id_]: x for x in vieilles.get(cle, [])}
        for x in nouveau["sorties"][cle]:
            connus[x[id_]] = {**connus.get(x[id_], {}), **{k: v for k, v in x.items() if v}}
        nouveau["sorties"][cle] = list(connus.values())
    noms = {(f["nom"], f.get("legende")) for f in vieilles.get("fichiers", [])}
    nouveau["sorties"]["fichiers"] = vieilles.get("fichiers", []) + [
        f for f in nouveau["sorties"]["fichiers"] if (f["nom"], f.get("legende")) not in noms
    ]
    nouveau["branches"] = sorted(set(ancien.get("branches", [])) | set(nouveau["branches"]))
    nouveau["dernier_evenement"] = nouveau.get("dernier_evenement") or ancien.get("dernier_evenement")
    return nouveau


def construire(meta: dict, evts: list[dict]) -> dict:
    sid = meta["id"]
    entrees, sorties, branches = analyser(evts)
    ctx = meta.get("session_context") or {}
    ext = meta.get("external_metadata") or {}
    resume = meta.get("post_turn_summary") or ext.get("post_turn_summary") or {}
    depots = sorted({s["git_repository"]["url"].removeprefix("https://github.com/")
                     for s in ctx.get("sources", []) if s.get("git_repository", {}).get("url")})
    for o in ctx.get("outcomes", []):
        branches.update((o.get("git_repository", {}).get("git_info") or {}).get("branches", []))
    statut = "archivée" if meta.get("session_status") == "SESSION_STATUS_ARCHIVED" else STATUTS.get(meta.get("status_bucket"), "terminée")
    return {
        "id": sid,
        "titre": meta.get("title") or "(sans titre)",
        "url": f"https://claude.ai/code/{sid}",
        "cree_le": meta.get("created_at"),
        "maj_le": meta.get("updated_at") or meta.get("created_at"),
        "statut": statut,
        "a_faire": masquer(resume.get("needs_action") or "") or None,
        "dernier_resultat": masquer(resume.get("recent_action") or meta.get("task_summary") or "") or None,
        "cout_usd": (ext.get("usage") or {}).get("cost_usd"),
        "depots": depots,
        "branches": sorted(branches),
        "entrees": entrees,
        "sorties": {
            "prs": sorties["prs"],
            "artifacts": [{"titre": a.get("title") or "Artifact", "url": a["url"]} for a in ext.get("artifacts", []) if a.get("url")],
            "fichiers": sorties["fichiers"],
            "commits": sorties["commits"],
        },
        "dernier_evenement": next((e["user"]["uuid"] for e in reversed(evts) if e.get("user")), None),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sessions", type=Path, required=True)
    ap.add_argument("--pages", type=Path, required=True)
    ap.add_argument("--precedent", type=Path)
    ap.add_argument("--sortie", type=Path, required=True)
    a = ap.parse_args()

    precedent = {}
    if a.precedent and a.precedent.exists():
        precedent = {s["id"]: s for s in json.loads(a.precedent.read_text()).get("sessions", [])}
    metas = {m["id"]: m for m in sessions_de(a.sessions) if str(m.get("id", "")).startswith("session_")}
    index = []
    for sid, meta in metas.items():
        s = fusionner(precedent.get(sid), construire(meta, evenements(a.pages, sid)))
        s["entrees"].sort(key=lambda e: e["le"])
        index.append(s)
        print(f"{s['titre'][:50]:50} {len(s['entrees']):4} messages  {len(s['sorties']['prs']):3} PR", file=sys.stderr)
    # Sessions disparues de la liste (supprimées) : gardées telles quelles
    index += [s for sid, s in precedent.items() if sid not in metas]
    sortie = {"genere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sessions": index}
    a.sortie.write_text(json.dumps(sortie, ensure_ascii=False))
    print(f"{len(index)} sessions → {a.sortie} ({a.sortie.stat().st_size // 1024} Ko)", file=sys.stderr)


if __name__ == "__main__":
    main()
