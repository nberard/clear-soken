"""Lecture des mails de commande des boutiques de CBD (texte brut du mail -> lignes produit).

Testé sur les confirmations de commande PrestaShop : chaque produit occupe une ligne
« Nom - Type - Choisir une quantité : 3gr », suivie du prix unitaire, de la quantité et du total.
Pour une boutique au format inconnu, on se rabat sur les molécules citées dans tout le mail.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from . import substances as sb

PRIX = re.compile(r"^-?\d[\d\s.]*,\d{2}\s?€$")
ENTIER = re.compile(r"^\d{1,3}$")
GRAMMES = re.compile(r"(\d+(?:[.,]\d+)?)\s?(?:gr|g|grammes?)\b", re.I)
MG = re.compile(r"(\d+(?:[.,]\d+)?)\s?mg\b", re.I)
FIN_PRODUITS = re.compile(r"^(Produits|Sous-total|Total)\b", re.I)



def boutiques_depuis(texte: str) -> dict[str, str | None]:
    """« boutique-a.fr,boutique-b.fr:cbd » -> {domaine: molécule par défaut si rien n'est lisible}."""
    out: dict[str, str | None] = {}
    for item in texte.split(","):
        dom, _, defaut = item.strip().partition(":")
        if dom:
            out[dom.lower()] = defaut.strip() or None
    return out


# Boutiques suivies : dans .env (CONSO_BOUTIQUES), jamais dans le dépôt.
BOUTIQUES = boutiques_depuis(os.environ.get("CONSO_BOUTIQUES", ""))


@dataclass
class Ligne:
    produit: str
    substances: list[str]
    quantite: int = 1
    grammes: float | None = None
    mg: float | None = None
    prix: float | None = None


@dataclass
class Commande:
    boutique: str
    lignes: list[Ligne] = field(default_factory=list)
    total: float | None = None

    @property
    def substances(self) -> list[str]:
        vus: list[str] = []
        for ligne in self.lignes:
            for s in ligne.substances:
                if s not in vus:
                    vus.append(s)
        return vus


def _boutique_legale(subs: list[str], boutique: str) -> list[str]:
    """Une boutique légale en France ne vend pas de THC « delta-9 » : « CBC + THC » sur une vape
    désigne un THC semi-synthétique, compté comme THC-X (modifiable dans conso_substances)."""
    if boutique in BOUTIQUES and "thc" in subs:
        subs = ["thcx" if s == "thc" else s for s in subs]
        return list(dict.fromkeys(subs))
    return subs


def _prix(s: str) -> float:
    return float(s.replace("€", "").replace(" ", "").replace(".", "").replace(",", "."))


def boutique_de(expediteur: str, sujet: str = "") -> str | None:
    texte = f"{expediteur} {sujet}".lower()
    for domaine in BOUTIQUES:
        if domaine in texte or domaine.split(".")[0] in texte.replace(" ", ""):
            return domaine
    return None


def est_confirmation(sujet: str) -> bool:
    """Un seul mail par commande : on ignore « Paiement accepté », relances, avis, newsletters."""
    s = sb.normaliser(sujet)
    if any(m in s for m in ("panier", "avis", "moment de passer", "destockage", "paiement accepte")):
        return False
    return "commande" in s or "order" in s


def lire(texte: str, boutique: str) -> Commande:
    cmd = Commande(boutique)
    lignes = [l.strip() for l in texte.splitlines()]
    lignes = [l for l in lignes if l]
    i = 0
    while i < len(lignes):
        l = lignes[i]
        if FIN_PRODUITS.match(l) and cmd.lignes:
            break
        # Ligne produit : du texte avec « - », suivie de prix / quantité / total
        if (
            " - " in l
            and not PRIX.match(l)
            and i + 3 < len(lignes)
            and PRIX.match(lignes[i + 1])
            and ENTIER.match(lignes[i + 2])
            and PRIX.match(lignes[i + 3])
        ):
            subs = _boutique_legale(sb.molecules(l), boutique)
            g = GRAMMES.search(l)
            mg = MG.search(l)
            q = int(lignes[i + 2])
            cmd.lignes.append(
                Ligne(
                    produit=l.rstrip(" -"),
                    substances=subs,
                    quantite=q,
                    grammes=float(g.group(1).replace(",", ".")) * q if g else None,
                    mg=float(mg.group(1).replace(",", ".")) * q if mg else None,
                    prix=_prix(lignes[i + 3]),
                )
            )
            i += 4
            continue
        i += 1
    m = re.search(r"Total pay[ée]\s+(\d[\d\s.]*,\d{2})\s?€", texte)
    if m:
        cmd.total = _prix(m.group(1))
    if not cmd.lignes:
        # Format inconnu : molécules citées dans le mail, sinon la molécule par défaut de la boutique
        subs = sb.molecules(texte) or ([BOUTIQUES[boutique]] if BOUTIQUES.get(boutique) else [])
        if subs:
            cmd.lignes.append(Ligne(produit="(détail non lu)", substances=subs))
    return cmd
