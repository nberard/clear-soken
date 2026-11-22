"""Historique de conso depuis les exports WhatsApp, traité sur le PC (le texte ne quitte pas le PC).

    python3 mint-health/sync/healthsync/whatsapp_import.py ~/imports/whatsapp --moi "Ton nom" --essai
    python3 mint-health/sync/healthsync/whatsapp_import.py ~/imports/whatsapp --moi "Ton nom"

Lit les exports « .txt » (ou les « .zip » de WhatsApp) d'un dossier, repère les mentions de
cannabinoïdes (même détection que les notifications MacroDroid) et envoie à mint-health
seulement : date, molécule, type (achat / conso / mention), mots repérés, auteur moi/autre.
Le nom des contacts et le texte des messages ne sont pas envoyés.

Destination et jeton : variables HEALTH_URL (ex. https://health.example.fr/health/api) et
CONSO_INGEST_TOKEN, sinon lus dans mint-health/.env (HEALTH_HOST, CONSO_INGEST_TOKEN).
Bibliothèque standard uniquement : aucun paquet à installer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))
import substances as sb  # noqa: E402  (import direct : pas de dépendance au paquet healthsync)

# « 22/11/2026 23:30 - Nom: msg » (Android), « [22/11/2026 23:30:12] Nom: msg » (iPhone),
# « 22/11/26, 23:30 - Nom: msg » (autres langues).
LIGNE = re.compile(
    r"^‎?\[?(\d{1,2})[/.](\d{1,2})[/.](\d{2,4}),?\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(?:[AaPp][Mm])?\]?"
    r"\s*(?:-\s*)?([^:]{1,80}?):\s(.*)$"
)


def lire_lignes(chemin: Path) -> Iterator[tuple[str, list[str]]]:
    """(nom de la conversation, lignes) pour chaque export du dossier, zips compris."""
    fichiers = [chemin] if chemin.is_file() else sorted(chemin.rglob("*"))
    for f in fichiers:
        if f.suffix.lower() == ".txt":
            yield f.stem, f.read_text(encoding="utf-8", errors="replace").splitlines()
        elif f.suffix.lower() == ".zip":
            with zipfile.ZipFile(f) as z:
                for n in z.namelist():
                    if n.lower().endswith(".txt"):
                        yield f"{f.stem}/{n}", z.read(n).decode("utf-8", "replace").splitlines()


def messages(lignes: list[str], mdy: bool = False) -> Iterator[tuple[datetime, str, str]]:
    """(date, auteur, texte) ; les lignes de suite sont rattachées au message précédent."""
    courant = None
    for l in lignes:
        m = LIGNE.match(l.strip("﻿"))
        if m:
            if courant:
                yield courant
            a, b, y, hh, mm, ss, auteur, texte = m.groups()
            jour, mois = (int(b), int(a)) if mdy else (int(a), int(b))
            an = int(y) + 2000 if len(y) == 2 else int(y)
            try:
                at = datetime(an, mois, jour, int(hh), int(mm), int(ss or 0))
            except ValueError:
                courant = None
                continue
            courant = (at, auteur.strip("‎ "), texte)
        elif courant:
            courant = (courant[0], courant[1], courant[2] + "\n" + l)
    if courant:
        yield courant


def evenements(dossier: Path, moi: list[str], mdy: bool = False, depuis: datetime | None = None) -> list[dict]:
    moi_n = {sb.normaliser(m) for m in moi}
    out = []
    for conv, lignes in lire_lignes(dossier):
        for at, auteur, texte in messages(lignes, mdy):
            if depuis and at < depuis:
                continue
            if "<Médias omis>" in texte or "<Media omitted>" in texte:
                continue
            det = sb.detecter_message(texte)
            if not det:
                continue
            est_moi = sb.normaliser(auteur) in moi_n
            ref = hashlib.sha256(f"{conv}\x1f{at.isoformat()}\x1f{auteur}\x1f{texte}".encode()).hexdigest()[:32]
            for s in det.substances:
                out.append({
                    "at": at.isoformat(), "substance": s, "kind": det.kind, "ref": ref,
                    "mots": det.mots[:20], "auteur": "moi" if est_moi else "autre",
                })
    return out


def lire_env() -> dict:
    env = {}
    f = Path(__file__).resolve().parents[2] / ".env"
    if f.exists():
        for l in f.read_text().splitlines():
            if "=" in l and not l.lstrip().startswith("#"):
                k, v = l.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def envoyer(evts: list[dict], url: str, jeton: str) -> None:
    for i in range(0, len(evts), 2000):
        lot = evts[i:i + 2000]
        req = urllib.request.Request(
            f"{url.rstrip('/')}/ingest/conso",
            data=json.dumps({"source": "whatsapp", "evenements": lot}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {jeton}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            print(f"  lot {i // 2000 + 1} : {json.loads(r.read())}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("dossier", type=Path, help="dossier des exports WhatsApp (.txt / .zip)")
    p.add_argument("--moi", action="append", default=[], help="ton nom tel qu'il apparaît dans les exports (répétable)")
    p.add_argument("--mdy", action="store_true", help="dates au format mois/jour (exports en anglais US)")
    p.add_argument("--depuis", default="2020-01-01", help="ignorer les messages plus anciens (AAAA-MM-JJ)")
    p.add_argument("--essai", action="store_true", help="résumé seulement, rien n'est envoyé")
    p.add_argument("--sortie", type=Path, help="écrire aussi les événements dans ce fichier JSON (à vérifier)")
    a = p.parse_args()
    if not a.dossier.exists():
        sys.exit(f"Introuvable : {a.dossier}")

    evts = evenements(a.dossier, a.moi, a.mdy, datetime.fromisoformat(a.depuis))
    par_mois = Counter((e["at"][:7], e["kind"]) for e in evts)
    mois = sorted({m for m, _ in par_mois})
    print(f"{len(evts)} événement(s) détecté(s) sur {len(mois)} mois")
    print("mois      achat  conso  mention")
    for m in mois:
        print(f"{m}  {par_mois[(m, 'achat')]:5}  {par_mois[(m, 'conso')]:5}  {par_mois[(m, 'mention')]:7}")
    print("molécules :", dict(Counter(e["substance"] for e in evts)))
    if not a.moi:
        print("Astuce : --moi \"Ton nom\" distingue tes messages de ceux des autres.")
    if a.sortie:
        a.sortie.write_text(json.dumps(evts, ensure_ascii=False, indent=1))
        print(f"Écrit : {a.sortie}")
    if a.essai:
        return

    env = lire_env()
    url = os.environ.get("HEALTH_URL") or (f"https://{env['HEALTH_HOST']}/health/api" if env.get("HEALTH_HOST") else "")
    jeton = os.environ.get("CONSO_INGEST_TOKEN") or env.get("CONSO_INGEST_TOKEN", "")
    if not url or not jeton:
        sys.exit("Indique HEALTH_URL et CONSO_INGEST_TOKEN (variables d'environnement ou mint-health/.env).")
    print(f"Envoi vers {url} …")
    envoyer(evts, url, jeton)


if __name__ == "__main__":
    main()
