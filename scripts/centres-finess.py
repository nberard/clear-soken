#!/usr/bin/env python3
"""Génère backend/data/centres.json : les centres d'addictologie de France (CSAPA, CAARUD) avec leurs coordonnées.

Source : FINESS, fichier des établissements géolocalisés publié sur data.gouv.fr (Licence Ouverte).
    python3 scripts/centres-finess.py                       # télécharge la dernière extraction
    python3 scripts/centres-finess.py --fichier finess.csv  # ou un fichier déjà téléchargé
Puis `make restart` pour que l'API serve le nouvel annuaire. Python 3.9+, sans dépendance.

Les lieux conseillés par l'équipe (consultation hospitalière, groupe de parole…) se mettent à la main
dans backend/data/centres-equipe.json, que ce script ne touche jamais.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import sys
import urllib.request
from pathlib import Path

DATASET_API = "https://www.data.gouv.fr/api/1/datasets/finess-extraction-du-fichier-des-etablissements/"
SORTIE = Path(__file__).resolve().parent.parent / "backend" / "data" / "centres.json"

# Catégories FINESS (categetab)
CATEGORIES = {
    "197": "csapa",  # Centre de soins, d'accompagnement et de prévention en addictologie
    "178": "caarud",  # Centre d'accueil et d'accompagnement à la réduction des risques pour usagers de drogues
}

# Colonnes des lignes « structureet » et « geolocalisation » (format etalab cs1100507)
S_FINESS, S_RS, S_RSLONGUE, S_COMPLRS = 1, 3, 4, 5
S_NUMVOIE, S_TYPVOIE, S_VOIE, S_COMPVOIE, S_LIEUDIT = 7, 8, 9, 10, 11
S_ACHEMINEMENT, S_TEL, S_CATEGORIE = 15, 16, 18
G_FINESS, G_X, G_Y = 1, 2, 3

TYPES_VOIE = {
    "R": "rue", "AV": "avenue", "BD": "boulevard", "PL": "place", "CHE": "chemin", "RTE": "route",
    "ALL": "allée", "IMP": "impasse", "QUAI": "quai", "CRS": "cours", "SQ": "square", "PAS": "passage",
    "FG": "faubourg", "QU": "quai", "PROM": "promenade", "RES": "résidence", "LOT": "lotissement",
}

# --- Projections : Lambert 93 (métropole, Corse) et UTM (outre-mer) vers WGS84 ---

E_GRS80 = 0.08181919104281579
A_GRS80 = 6378137.0


def lambert93_vers_wgs84(x: float, y: float) -> tuple[float, float]:
    """Inverse de la projection conique conforme Lambert 93 (constantes IGN)."""
    n, c, xs, ys, lon0 = 0.7256077650532670, 11754255.426096, 700000.0, 12655612.049876, math.radians(3)
    dx, dy = x - xs, y - ys
    r = math.hypot(dx, dy)
    gamma = math.atan2(dx, -dy)
    lon = lon0 + gamma / n
    iso = -math.log(r / c) / n
    lat = 2 * math.atan(math.exp(iso)) - math.pi / 2
    for _ in range(12):
        es = E_GRS80 * math.sin(lat)
        lat = 2 * math.atan(((1 + es) / (1 - es)) ** (E_GRS80 / 2) * math.exp(iso)) - math.pi / 2
    return math.degrees(lat), math.degrees(lon)


def utm_vers_wgs84(x: float, y: float, zone: int, sud: bool) -> tuple[float, float]:
    """Inverse de la projection UTM (série de Krüger, précision métrique)."""
    a, f, k0 = A_GRS80, 1 / 298.257222101, 0.9996
    n = f / (2 - f)
    big_a = a / (1 + n) * (1 + n**2 / 4 + n**4 / 64)
    beta = [n / 2 - 2 * n**2 / 3 + 37 * n**3 / 96, n**2 / 48 + n**3 / 15, 17 * n**3 / 480]
    delta = [2 * n - 2 * n**2 / 3 - 2 * n**3, 7 * n**2 / 3 - 8 * n**3 / 5, 56 * n**3 / 15]
    xi = (y - (10000000.0 if sud else 0.0)) / (k0 * big_a)
    eta = (x - 500000.0) / (k0 * big_a)
    xi_p = xi - sum(b * math.sin(2 * j * xi) * math.cosh(2 * j * eta) for j, b in enumerate(beta, 1))
    eta_p = eta - sum(b * math.cos(2 * j * xi) * math.sinh(2 * j * eta) for j, b in enumerate(beta, 1))
    chi = math.asin(math.sin(xi_p) / math.cosh(eta_p))
    lat = chi + sum(d * math.sin(2 * j * chi) for j, d in enumerate(delta, 1))
    lon = math.radians(zone * 6 - 183) + math.atan2(math.sinh(eta_p), math.cos(xi_p))
    return math.degrees(lat), math.degrees(lon)


# Outre-mer : projection selon le début du code postal
UTM_OUTRE_MER = {
    "971": (20, False), "977": (20, False), "978": (20, False), "972": (20, False),
    "973": (22, False), "974": (40, True), "975": (21, False), "976": (38, True),
}


def vers_wgs84(x: float, y: float, cp: str) -> tuple[float, float] | None:
    zone = UTM_OUTRE_MER.get(cp[:3]) if cp.startswith("97") else None
    lat, lon = utm_vers_wgs84(x, y, *zone) if zone else lambert93_vers_wgs84(x, y)
    if zone is None and not (41 <= lat <= 51.5 and -5.5 <= lon <= 10):
        return None  # hors métropole : coordonnée douteuse
    return round(lat, 5), round(lon, 5)


# --- Mise en forme ---


def joli(texte: str, majuscule: bool = True) -> str:
    """« CSAPA DE L'HOPITAL ST JEAN » -> « Csapa de l'Hopital St Jean » (sigles connus gardés)."""
    petits = {"de", "du", "des", "la", "le", "les", "et", "en", "à", "au", "aux", "d", "l", "sur"}
    sigles = {"CSAPA", "CAARUD", "CJC", "CHU", "CH", "CHS", "CHI", "CHR", "CMP", "ANPAA", "ELSA", "AIDES", "SOS", "CMPP", "GHU", "APHP", "AP-HP", "EPSM", "SSR"}
    mots = re.split(r"(\s+|-|')", texte.strip())
    out = []
    for i, m in enumerate(mots):
        if m.upper() in sigles:
            out.append(m.upper())
        elif m.lower() in petits and (i or not majuscule):
            out.append(m.lower())
        else:
            out.append(m[:1].upper() + m[1:].lower())
    return re.sub(r"\s+", " ", "".join(out))


def telephone(brut: str) -> str | None:
    chiffres = re.sub(r"\D", "", brut or "")
    if len(chiffres) != 10:
        return None
    return " ".join(chiffres[i : i + 2] for i in range(0, 10, 2))


def specialites(nom: str) -> list[str]:
    """Indices dans le nom : un CSAPA « alcool » ou « tabac » est spécialisé, sinon il prend toutes les addictions."""
    n = nom.upper()
    spe = []
    if re.search(r"ALCOOL", n):
        spe.append("alcool")
    if re.search(r"TABAC", n):
        spe.append("tabac")
    if re.search(r"TOXICOMAN|DROGUES? ILLICITE", n):
        spe += ["cannabis", "cocaine", "opioides"]
    return spe


def centre(s: list[str], xy: tuple[str, str]) -> dict | None:
    acheminement = s[S_ACHEMINEMENT].strip()
    m = re.match(r"(\d{5})\s+(.*)", acheminement)
    if not m:
        return None
    cp, ville = m.group(1), m.group(2)
    try:
        pos = vers_wgs84(float(xy[0]), float(xy[1]), cp)
    except (ValueError, ZeroDivisionError):
        return None
    if not pos:
        return None
    nom_brut = (s[S_RSLONGUE] or s[S_RS]).strip()
    type_ = CATEGORIES[s[S_CATEGORIE].strip()]
    if type_ == "csapa" and re.search(r"\bCJC\b|JEUNES? CONSOMMATEUR", nom_brut.upper()):
        type_ = "cjc"
    voie = " ".join(
        p for p in [s[S_NUMVOIE].strip(), TYPES_VOIE.get(s[S_TYPVOIE].strip().upper(), s[S_TYPVOIE].strip().lower()), joli(s[S_VOIE], majuscule=False)] if p
    )
    adresse = ", ".join(p for p in [voie, joli(s[S_COMPVOIE]) if s[S_COMPVOIE].strip() else "", joli(s[S_LIEUDIT]) if s[S_LIEUDIT].strip() else ""] if p)
    out = {
        "id": s[S_FINESS].strip(),
        "nom": joli(nom_brut),
        "type": type_,
        "adresse": adresse or joli(s[S_COMPLRS]) or "",
        "cp": cp,
        "ville": joli(re.sub(r"\s+CEDEX.*$", "", ville, flags=re.I)),
        "tel": telephone(s[S_TEL]),
        "lat": pos[0],
        "lon": pos[1],
    }
    spe = specialites(nom_brut) if type_ == "csapa" else []
    if spe:
        out["specialites"] = spe
    return out


# --- Lecture du fichier FINESS ---


def url_finess() -> str:
    with urllib.request.urlopen(DATASET_API, timeout=60) as r:
        ressources = json.load(r)["resources"]
    for res in ressources:
        if "cs1100507" in res["url"] or ("géolocalisés" in res["title"].lower() and "établissements" in res["title"].lower()):
            return res["url"]
    raise SystemExit("Fichier FINESS géolocalisé introuvable sur data.gouv.fr : télécharge-le et passe --fichier")


def lire(texte: str) -> list[dict]:
    structures: dict[str, list[str]] = {}
    coords: dict[str, tuple[str, str]] = {}
    for ligne in csv.reader(io.StringIO(texte), delimiter=";"):
        if not ligne:
            continue
        if ligne[0] == "structureet" and len(ligne) > S_CATEGORIE and ligne[S_CATEGORIE].strip() in CATEGORIES:
            structures[ligne[S_FINESS].strip()] = ligne
        elif ligne[0] == "geolocalisation" and len(ligne) > G_Y:
            coords[ligne[G_FINESS].strip()] = (ligne[G_X], ligne[G_Y])
    out, sans_coord = [], 0
    for finess, s in structures.items():
        c = centre(s, coords[finess]) if finess in coords else None
        if c:
            out.append(c)
        else:
            sans_coord += 1
    print(f"{len(structures)} centres trouvés, {sans_coord} ignorés (sans coordonnées valides)", file=sys.stderr)
    return sorted(out, key=lambda c: (c["cp"], c["nom"]))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fichier", help="fichier FINESS déjà téléchargé (etalab-cs1100507-stock-….csv)")
    p.add_argument("--url", help="URL du fichier FINESS (par défaut : trouvée via l'API data.gouv.fr)")
    p.add_argument("--sortie", default=str(SORTIE))
    args = p.parse_args()

    if args.fichier:
        brut = Path(args.fichier).read_bytes()
    else:
        url = args.url or url_finess()
        print(f"Téléchargement de {url}", file=sys.stderr)
        with urllib.request.urlopen(url, timeout=300) as r:
            brut = r.read()
    try:
        texte = brut.decode("utf-8")
    except UnicodeDecodeError:
        texte = brut.decode("latin-1")

    centres = lire(texte)
    if len(centres) < 100:
        raise SystemExit(f"Seulement {len(centres)} centres lus : format FINESS inattendu, {args.sortie} n'est pas modifié")
    Path(args.sortie).write_text(json.dumps(centres, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    par_type: dict[str, int] = {}
    for c in centres:
        par_type[c["type"]] = par_type.get(c["type"], 0) + 1
    print(f"-> {args.sortie} : {len(centres)} centres {par_type}", file=sys.stderr)


if __name__ == "__main__":
    main()
