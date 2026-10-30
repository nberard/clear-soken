"""Import de l'historique Google Fit depuis un export Google Takeout (zips ou dossier décompressé).

    docker compose run --rm -v ~/takeout:/takeout:ro sync python -m healthsync.takeout /takeout
    docker compose run --rm -v ~/takeout:/takeout:ro sync python -m healthsync.takeout /takeout --essai

Lit « Fit/Métriques d'activité quotidiennes » (ou « Fit/Daily activity metrics » en anglais) : le résumé
par jour s'il existe, sinon les fichiers d'un jour (tranches de 15 min) additionnés. Écrit dans daily_metrics
avec la source « takeout », la dernière par défaut dans SOURCE_PRIORITY : l'historique remplit les jours
vides sans jamais remplacer ce que Google Health ou Health Connect ont synchronisé.
"""
import argparse
import asyncio
import csv
import io
import re
import sys
import unicodedata
import zipfile
from datetime import date
from pathlib import Path
from typing import Iterator

SOURCE = "takeout"
# « Métriques d'activité quotidiennes » : Google remplace l'apostrophe par « _ » dans les zips
DOSSIER_FIT = re.compile(r"(^|/)Fit/(M[ée]triques d.activit[ée] quotidiennes|Daily activity metrics)/", re.I)


def nom_zip(info: zipfile.ZipInfo) -> str:
    """Nom d'un fichier du zip, accents corrects. Les zips Takeout n'indiquent pas toujours que les noms sont en
    UTF-8 : Python les lit alors en cp437 (« M├⌐triques »). Les accents peuvent aussi être décomposés (e + ´)."""
    nom = info.filename
    if not info.flag_bits & 0x800:
        try:
            nom = nom.encode("cp437").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return unicodedata.normalize("NFC", nom)
JOUR = re.compile(r"(\d{4}-\d{2}-\d{2})\.csv$")

# Colonne (français ou anglais) -> (métrique de mint-health, conversion, agrégation sur la journée)
COLONNES = [
    (r"^nombre de pas$|^step count$", "steps.countSum", 1, "somme"),
    (r"^distance \(m\)$", "distance.millimetersSum", 1000, "somme"),
    (r"^calories \(kcal\)$", "total-calories.kcalSum", 1, "somme"),
    (r"fr[ée]quence cardiaque moyenne|^average heart rate", "heart-rate.beatsPerMinuteAvg", 1, "moyenne"),
    (r"fr[ée]quence cardiaque maximale|^max heart rate", "heart-rate.beatsPerMinuteMax", 1, "max"),
    (r"fr[ée]quence cardiaque minimale|^min heart rate", "heart-rate.beatsPerMinuteMin", 1, "min"),
    (r"^poids moyen|^average weight", "weight.kilograms", 1, "moyenne"),
]


def _colonnes(entete: list[str]) -> dict[int, tuple[str, float, str]]:
    out = {}
    for i, nom in enumerate(entete):
        nom = nom.strip().lower()
        for motif, metrique, facteur, agg in COLONNES:
            if re.search(motif, nom):
                out[i] = (metrique, facteur, agg)
                break
    return out


def _nombre(texte: str) -> float | None:
    texte = texte.strip().replace(",", ".")
    try:
        return float(texte) if texte else None
    except ValueError:
        return None


def _agreger(valeurs: dict[str, list[float]], aggs: dict[str, str]) -> dict[str, float]:
    out = {}
    for metrique, xs in valeurs.items():
        if not xs:
            continue
        agg = aggs[metrique]
        out[metrique] = (sum(xs) if agg == "somme" else sum(xs) / len(xs) if agg == "moyenne"
                         else max(xs) if agg == "max" else min(xs))
    return out


def lire_jour(texte: str) -> dict[str, float]:
    """Fichier d'une journée (une ligne par tranche de 15 min) -> totaux du jour."""
    lignes = list(csv.reader(io.StringIO(texte)))
    if not lignes:
        return {}
    cols = _colonnes(lignes[0])
    valeurs: dict[str, list[float]] = {m: [] for m, _, _ in cols.values()}
    for ligne in lignes[1:]:
        for i, (metrique, facteur, _) in cols.items():
            if i < len(ligne):
                v = _nombre(ligne[i])
                if v is not None:
                    valeurs[metrique].append(v * facteur)
    return _agreger(valeurs, {m: a for m, _, a in cols.values()})


def lire_resume(texte: str) -> dict[date, dict[str, float]]:
    """Fichier résumé (une ligne par jour, colonne Date) -> {jour: métriques}."""
    lignes = list(csv.reader(io.StringIO(texte)))
    if not lignes or lignes[0][0].strip().lower() != "date":
        return {}
    cols = _colonnes(lignes[0])
    out: dict[date, dict[str, float]] = {}
    for ligne in lignes[1:]:
        try:
            jour = date.fromisoformat(ligne[0].strip())
        except (ValueError, IndexError):
            continue
        metriques = {}
        for i, (metrique, facteur, _) in cols.items():
            v = _nombre(ligne[i]) if i < len(ligne) else None
            if v is not None:
                metriques[metrique] = v * facteur
        if metriques:
            out[jour] = metriques
    return out


def _fichiers(chemins: list[Path]) -> Iterator[tuple[str, bytes]]:
    """(nom, contenu) des CSV Fit, dans les zips comme dans les dossiers décompressés."""
    for chemin in chemins:
        if chemin.is_dir():
            yield from _fichiers(sorted(p for p in chemin.rglob("*") if p.suffix.lower() in (".zip", ".csv")))
        elif chemin.suffix.lower() == ".zip":
            with zipfile.ZipFile(chemin) as z:
                for info in z.infolist():
                    nom = nom_zip(info)
                    if DOSSIER_FIT.search(nom) and nom.lower().endswith(".csv"):
                        yield nom, z.read(info)
        elif chemin.suffix.lower() == ".csv" and DOSSIER_FIT.search(unicodedata.normalize("NFC", chemin.as_posix())):
            yield chemin.as_posix(), chemin.read_bytes()


def _noms_fit(chemins: list[Path]) -> Iterator[str]:
    """Noms des fichiers sous Fit/ (diagnostic quand rien n'est reconnu)."""
    for chemin in chemins:
        zips = sorted(chemin.glob("*.zip")) if chemin.is_dir() else [chemin]
        for z in zips:
            if z.suffix.lower() != ".zip":
                continue
            with zipfile.ZipFile(z) as f:
                for info in f.infolist():
                    nom = nom_zip(info)
                    if "/Fit/" in nom and not nom.endswith("/"):
                        yield nom.rsplit("/", 1)[0] + "/"


def collecter(chemins: list[Path]) -> dict[date, dict[str, float]]:
    par_jour: dict[date, dict[str, float]] = {}
    resume: dict[date, dict[str, float]] = {}
    for nom, contenu in _fichiers(chemins):
        texte = contenu.decode("utf-8-sig", errors="replace")
        m = JOUR.search(nom)
        if m:
            metriques = lire_jour(texte)
            if metriques:
                par_jour.setdefault(date.fromisoformat(m.group(1)), {}).update(metriques)
        else:
            resume.update(lire_resume(texte))
    # Le résumé de Google fait foi ; les fichiers d'un jour comblent ce qu'il n'a pas
    for jour, metriques in resume.items():
        par_jour.setdefault(jour, {}).update(metriques)
    return par_jour


async def importer(par_jour: dict[date, dict[str, float]]) -> int:
    from . import store

    await store.init()
    lignes = [(j, m, v) for j, ms in sorted(par_jour.items()) for m, v in ms.items()]
    for i in range(0, len(lignes), 5000):
        await store.upsert_metrics(lignes[i : i + 5000], source=SOURCE)
    await store.log("takeout", True, len(lignes), f"{len(par_jour)} jours importés depuis Google Takeout")
    return len(lignes)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("chemins", nargs="+", type=Path, help="zips Takeout ou dossier qui les contient")
    p.add_argument("--essai", action="store_true", help="affiche ce qui serait importé, sans écrire dans la base")
    args = p.parse_args()

    par_jour = collecter(args.chemins)
    if not par_jour:
        print("Aucune donnée Fit trouvée (dossier « Fit/Métriques d'activité quotidiennes » absent ?)", file=sys.stderr)
        fit = sorted({n for n in _noms_fit(args.chemins)})[:8]
        if fit:
            print("Fichiers Fit vus dans les zips (pour comprendre) :", *fit, sep="\n  ", file=sys.stderr)
        return 1
    jours = sorted(par_jour)
    compte: dict[str, int] = {}
    for ms in par_jour.values():
        for m in ms:
            compte[m] = compte.get(m, 0) + 1
    print(f"{len(jours)} jours, du {jours[0]} au {jours[-1]}")
    for m, n in sorted(compte.items()):
        print(f"  {m:40} {n} jours")
    if args.essai:
        print("Essai : rien n'a été écrit.")
        return 0
    n = asyncio.run(importer(par_jour))
    print(f"{n} valeurs écrites (source « {SOURCE} »).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
