"""Ligne de commande.

  python -m memoire importer <fichier.json|.zip> [--source chatgpt|claude|gemini|mistral]
  python -m memoire traiter [--limite N]
  python -m memoire demander "ta question" [--casquette sante_mentale]
  python -m memoire arbre
  python -m memoire etat
"""
from __future__ import annotations

import argparse
import sys

from . import agent, config, db, importers, llm, pipeline


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="memoire")
    sp = p.add_subparsers(dest="cmd", required=True)
    i = sp.add_parser("importer", help="importe un export (json ou zip)")
    i.add_argument("fichiers", nargs="+")
    i.add_argument("--source", choices=["chatgpt", "claude", "gemini", "mistral"])
    t = sp.add_parser("traiter", help="classe/résume les nouvelles conversations et refait l'arbre")
    t.add_argument("--limite", type=int)
    t.add_argument("--tout", action="store_true", help="reclasse aussi les conversations déjà traitées")
    d = sp.add_parser("demander", help="pose une question à ta mémoire")
    d.add_argument("question")
    d.add_argument("--casquette", action="append")
    sp.add_parser("arbre", help="affiche l'arbre de contexte")
    sp.add_parser("etat", help="compte les conversations par statut")
    a = p.parse_args(argv)

    cfg = config.charger()
    conn = db.connecter(cfg.db_path)
    if a.cmd in ("traiter", "demander"):
        try:
            llm.construire(cfg)
        except llm.CleManquante as e:
            print(f"Erreur : {e}", file=sys.stderr)
            return 1

    if a.cmd == "importer":
        for f in a.fichiers:
            convs = importers.lire_fichier(f, a.source)
            if not convs:
                print(f"{f} : format non reconnu ou export vide", file=sys.stderr)
                continue
            print(f"{f} : {importers.enregistrer(conn, convs)}")
    elif a.cmd == "traiter":
        api, local = llm.construire(cfg)
        stats = pipeline.traiter_tout(conn, cfg, api, local, a.limite,
                                      lambda n, tot, cid, s: print(f"[{n}/{tot}] {cid} → {s}", flush=True),
                                      tout=a.tout)
        print(stats)
    elif a.cmd == "demander":
        api, local = llm.construire(cfg)
        r = agent.demander(conn, cfg, a.question, api, local, a.casquette)
        print(f"(casquettes : {', '.join(r.casquettes)} — modèle : {r.backend})\n\n{r.texte}")
    elif a.cmd == "arbre":
        for n in conn.execute("SELECT * FROM noeuds ORDER BY niveau != 'racine', casquette, niveau != 'casquette', titre"):
            retrait = {"racine": "", "casquette": "  ", "sujet": "    "}[n["niveau"]]
            etat = " (à refaire)" if n["a_refaire"] else ""
            print(f"{retrait}{n['titre']}{etat}")
    elif a.cmd == "etat":
        for r in conn.execute("SELECT statut, COUNT(*) n, SUM(sensible) s FROM conversations GROUP BY statut"):
            print(f"{r['statut']:18} {r['n']:6}  (dont sensibles : {r['s']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
