"""Estimation de l'humeur (-3 très bas … +3 trop haut) à partir des données du jour.

Régression ridge, réentraînée chaque nuit sur tes propres notes :
- note du soir d'un jour : poids 1 ;
- note moyenne d'un mois (Rétro) appliquée à chacun de ses jours sans note du soir : poids faible
  (POIDS_MOIS), puisque c'est un souvenir global, pas une mesure du jour.
Variables : écarts à ta moyenne des 30 jours précédents (sommeil, pas, FC au repos, VFC, messages
envoyés, messages de nuit) et leur carré — le carré laisse le modèle apprendre qu'un sommeil très court
peut aller avec une phase haute comme avec une phase basse — plus la conso psychoactive du jour.
Une donnée absente compte comme « jour habituel » (0). Ce n'est qu'un repère : il s'améliore avec les notes.
"""
from __future__ import annotations

import logging
from datetime import datetime

from . import conso, store

log = logging.getLogger("healthsync.modele")

VARIABLES = ["z_sommeil", "z_pas", "z_fc", "z_vfc", "z_envoyes", "z_nuit"]
CARRES = ["z_sommeil", "z_envoyes", "z_nuit"]
POIDS_MOIS = 0.15
RIDGE = 3.0
MIN_JOURS_NOTES = 14     # notes du soir
MIN_MOIS_NOTES = 6       # ou mois notés dans la Rétro


def _ligne(r: dict) -> list[float]:
    def v(k):
        x = r.get(k)
        return max(-4.0, min(4.0, float(x))) if x is not None else 0.0
    x = [v(k) for k in VARIABLES]
    x += [v(k) ** 2 for k in CARRES]
    x.append(float(r["conso"]) if r.get("conso") is not None else 0.0)
    return x


def noms() -> list[str]:
    return VARIABLES + [f"{k}²" for k in CARRES] + ["conso"]


def zone(estime: float, seuil: int) -> str:
    if estime <= -seuil:
        return "critique_bas"
    if estime >= seuil:
        return "critique_haut"
    if estime <= -1:
        return "bas"
    if estime >= 1:
        return "haut"
    return "stable"


def entrainer_sur(rows: list[dict]) -> dict | None:
    """rows : dicts de moral_quotidien. Renvoie {coefs, biais, n_jours, n_mois, r2} ou None."""
    import numpy as np

    X, y, w = [], [], []
    n_jours = n_mois_jours = 0
    mois_notes = set()
    for r in rows:
        if r.get("moral") is not None:
            X.append(_ligne(r)); y.append(float(r["moral"])); w.append(1.0); n_jours += 1
        elif r.get("moral_mois") is not None:
            X.append(_ligne(r)); y.append(float(r["moral_mois"])); w.append(POIDS_MOIS); n_mois_jours += 1
            mois_notes.add(r["day"].strftime("%Y-%m"))
    if n_jours < MIN_JOURS_NOTES and len(mois_notes) < MIN_MOIS_NOTES:
        return None
    X, y, w = np.array(X), np.array(y), np.array(w)
    moy = np.average(y, weights=w)
    Xw = X * np.sqrt(w)[:, None]
    yw = (y - moy) * np.sqrt(w)
    A = Xw.T @ Xw + RIDGE * np.eye(X.shape[1])
    coefs = np.linalg.solve(A, Xw.T @ yw)
    pred = X @ coefs + moy
    ss_res = float(np.sum(w * (y - pred) ** 2))
    ss_tot = float(np.sum(w * (y - moy) ** 2)) or 1.0
    return {
        "coefs": dict(zip(noms(), [round(float(c), 4) for c in coefs])),
        "biais": round(float(moy), 4),
        "n_jours": n_jours, "n_mois": len(mois_notes),
        "r2": round(1 - ss_res / ss_tot, 3),
    }


def predire(m: dict, r: dict) -> float:
    x = _ligne(r)
    e = m["biais"] + sum(c * xi for c, xi in zip([m["coefs"][k] for k in noms()], x))
    return max(-3.0, min(3.0, e))


async def entrainer() -> dict:
    async with await store.connect() as conn:
        cur = await conn.execute("SELECT * FROM moral_quotidien ORDER BY day")
        cols = [c.name for c in cur.description]
        rows = [dict(zip(cols, r)) for r in await cur.fetchall()]
    m = entrainer_sur(rows)
    if not m:
        return {"status": "pas_assez_de_notes",
                "besoin": f"{MIN_JOURS_NOTES} notes du soir ou {MIN_MOIS_NOTES} mois notés dans la Rétro"}
    seuil = int((await conso.reglages())["seuil_critique"])
    preds = [(r["day"], round(predire(m, r), 2)) for r in rows]
    async with await store.connect() as conn:
        async with conn.transaction():
            await conn.execute("TRUNCATE moral_estime")
            async with conn.cursor() as cur:
                await cur.executemany(
                    "INSERT INTO moral_estime (day, estime, zone) VALUES (%s, %s, %s)",
                    [(d, e, zone(e, seuil)) for d, e in preds],
                )
    m["date"] = datetime.now().isoformat(timespec="minutes")
    await conso.set_reglage("modele", m)
    await store.log("modele", True, len(preds), f"R² {m['r2']} · {m['n_jours']} jours notés · {m['n_mois']} mois")
    return {"status": "ok", **m}


@conso.router.post("/modele/entrainer")
async def route_entrainer():
    return await entrainer()
