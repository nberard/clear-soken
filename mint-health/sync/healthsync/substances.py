"""Catalogue des cannabinoïdes et détection dans un texte (commande, message, notification).

Module sans dépendance (bibliothèque standard uniquement) : il est aussi utilisé par le script
d'import WhatsApp lancé directement sur le PC (python3, sans Docker).

Psychoactivité : 0 = aucune, 1 = légère (relaxant, sédatif), 2 = nette, 3 = forte (proche du THC
ou plus). Les noms commerciaux récents (HPX, X2…) n'ont pas de composition publique fiable :
leur niveau est une estimation marquée « à confirmer », modifiable dans la table conso_substances.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# code -> (nom affiché, psychoactivité 0-3, effet résumé, à confirmer)
SUBSTANCES: dict[str, tuple[str, int, str, bool]] = {
    "thc": ("THC", 3, "euphorisant, psychoactif", False),
    "thcx": ("THC-X", 3, "semi-synthétique, effets proches du THC, parfois plus marqués", True),
    "thcp": ("THCP", 3, "semi-synthétique, très puissant", False),
    "hhcp": ("HHC-P", 3, "semi-synthétique, puissant", False),
    "hhc": ("HHC", 2, "semi-synthétique, psychoactif modéré", False),
    "hpx": ("HPX", 2, "molécule de synthèse récente, composition non publiée", True),
    "x2": ("Molécule X2", 2, "molécule de synthèse récente, composition non publiée", True),
    "h4cbd": ("H4-CBD", 1, "CBD hydrogéné, relaxant", False),
    "cbn": ("CBN", 1, "sédatif, aide au sommeil", False),
    "cbc": ("CBC", 1, "non euphorisant, humeur et anti-inflammatoire", False),
    "cbg": ("CBG", 0, "non psychoactif, concentration", False),
    "cbd": ("CBD", 0, "non psychoactif, relaxant", False),
}

# Seuil à partir duquel une prise compte comme « THC ou équivalent » pour le compteur.
SEUIL_PSYCHOACTIF = 2


def nom(code: str) -> str:
    return SUBSTANCES.get(code, (code.upper(),))[0]


def psychoactivite(code: str) -> int:
    return SUBSTANCES.get(code, ("", 0))[1]


def normaliser(texte: str) -> str:
    """Minuscules, sans accents, tirets/apostrophes uniformisés."""
    t = unicodedata.normalize("NFKD", texte)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t.lower().replace("’", "'").replace("–", "-").replace("—", "-")


# Molécules nommées explicitement (fiches produit, messages). L'ordre compte : les plus
# spécifiques d'abord, et chaque correspondance est retirée du texte avant les suivantes
# (« THC-X » ne doit pas compter aussi comme « THC »).
_MOLECULES: list[tuple[str, re.Pattern]] = [
    ("thcx", re.compile(r"\bthc[\s-]?x\b")),
    ("thcp", re.compile(r"\bthc[\s-]?p\b")),
    ("hhcp", re.compile(r"\bhhc[\s-]?p\b")),
    ("hhc", re.compile(r"\bhhc[\s-]?o?\b")),
    ("h4cbd", re.compile(r"\bh4[\s-]?cbd\b")),
    ("hpx", re.compile(r"\bhpx\b")),
    ("x2", re.compile(r"\bmolecules?\s+x2\b|\bx2\b")),
    ("cbn", re.compile(r"\bcbn\b")),
    ("cbc", re.compile(r"\bcbc\b")),
    ("cbg", re.compile(r"\bcbg\b")),
    ("cbd", re.compile(r"\bcbd\b")),
    ("thc", re.compile(r"\bthc\b|\bdelta[\s-]?9\b")),
]


def molecules(texte: str) -> list[str]:
    """Molécules citées dans un texte, dans l'ordre du catalogue, sans doublon."""
    t = normaliser(texte)
    trouve = []
    for code, rx in _MOLECULES:
        if rx.search(t):
            trouve.append(code)
            t = rx.sub(" ", t)
    return trouve


# --- Messages (WhatsApp, notifications) ---

# Mots qui désignent à coup sûr du cannabis « de rue » (donc THC).
_RUE_FORT = re.compile(
    r"\b(beuh|weed|teu?ch|teu?shi|bedos?|petards?|spliffs?|oinj|zeb|pochon|resine|hasch|haschich|"
    r"haschisch|marijuana|cannabis|ganja|kush|douilles?|joints?)\b"
)
# Ambigus seuls (« oh shit », « un joint de robinet ») : comptent seulement avec un autre indice.
_RUE_FAIBLE = re.compile(r"\b(shit|herbe|fumette|plaquette|barrette|savonnette|pets?|frappe|matos|bang)\b")
_ACHAT = re.compile(
    r"(t'?as (de la|du|encore)|\bdispo\b|je passe (prendre|chercher|recuperer)|"
    r"\bun (10|20|50|100)\b|\b(10|20|50|100) (balles|euros?|e)\b|combien le g\b|le g a\b|"
    r"\bcommande\b|\blivr|\bachete|\bpaye|\bramene|\bpecho|\bchoper|\bplan\b)"
)
_CONSO = re.compile(
    r"(\bfum|\bdefonc|\bperche|\bstone|\broul(e|er|ait)\b|\bun pet\b|\btaff|\bbuzz|"
    r"\bhigh\b|\bdefonce|\bvapot|\bvape\b|\bj'?\s?ai pris\b|\bconsomm)"
)


@dataclass
class Detection:
    kind: str  # achat | conso | mention
    substances: list[str]
    mots: list[str] = field(default_factory=list)


def detecter_message(texte: str) -> Detection | None:
    """Repère une mention de cannabinoïde dans un message. None si rien de suffisant.

    Conservateur : un mot ambigu (« shit ») ne suffit pas seul, il faut un indice d'achat
    ou de consommation. Le résultat est toujours de confiance « déduit ».
    """
    t = normaliser(texte)
    mols = molecules(t)
    fort = _RUE_FORT.findall(t)
    faible = _RUE_FAIBLE.findall(t)
    achat = _ACHAT.search(t)
    conso = _CONSO.search(t)
    # « 1 g », « 2g » : seulement comme indice d'achat avec un autre mot
    grammes = re.search(r"\b\d+([.,]\d+)?\s?g(r|rammes?)?\b", t)

    subs = list(mols)
    mots = [m.upper() for m in mols]
    if fort:
        mots += sorted(set(fort))
        if "thc" not in subs and not mols:
            subs.append("thc")
    if not subs and faible and (achat or conso or grammes):
        subs.append("thc")
        mots += sorted(set(faible))
    if not subs:
        return None
    if achat or (grammes and (fort or mols)):
        kind = "achat"
    elif conso:
        kind = "conso"
    else:
        kind = "mention"
    return Detection(kind, subs, mots)
