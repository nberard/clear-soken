"""Tests du suivi de conso et du moral.

Unitaires : toujours. API complète (vraie base) : seulement si TEST_DATABASE_URL est défini.
Les textes ci-dessous sont inventés (aucune donnée personnelle dans le dépôt).
"""
import os
from datetime import datetime, timedelta, timezone

import pytest


from healthsync import commandes, push, whatsapp_import  # noqa: E402
from healthsync import substances as sb  # noqa: E402

needs_db = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL non défini")

COMMANDE = """Bonjour,
Détails de la commande
Référence\tProduit\tPrix unitaire\tQuantité\tPrix total
Vape CBC + THC 1000mg - Saveur pêche -
39,90 €
1
39,90 €
Exemple - Fleurs HPX - Choisir une quantité : 3gr
32,00 €
2
64,00 €
Autre - Fleurs CBC - Choisir une quantité : 6gr
59,90 €
1
59,90 €
Produits\t163,80 €
Total payé\t163,80 €
"""


def test_molecules_specifiques_avant_generiques():
    assert sb.molecules("Vape THC-X 95%") == ["thcx"]
    assert sb.molecules("HHC-P et HHC") == ["hhcp", "hhc"]
    assert sb.molecules("Fleurs CBD") == ["cbd"]
    assert sb.molecules("Molécule X2") == ["x2"]


def test_detection_message_conservatrice():
    assert sb.detecter_message("oh shit j'ai raté le bus") is None
    assert sb.detecter_message("je passe prendre un 20") is None  # aucun mot de substance
    d = sb.detecter_message("t'as de la beuh dispo ce soir ?")
    assert d.kind == "achat" and d.substances == ["thc"]
    d = sb.detecter_message("on se fume un joint ?")
    assert d.kind == "conso"
    d = sb.detecter_message("j'ai pris 2g de shit")
    assert d.substances == ["thc"]
    assert sb.detecter_message("du HHC ou du CBD ?").kind == "mention"


def test_lecture_commande():
    cmd = commandes.lire(COMMANDE, "boutique-exemple.fr")
    assert len(cmd.lignes) == 3
    vape, hpx, cbc = cmd.lignes
    assert vape.substances == ["cbc", "thcx"]  # boutique légale : « THC » = THC semi-synthétique
    assert vape.mg == 1000
    assert hpx.grammes == 6 and hpx.quantite == 2
    assert cbc.substances == ["cbc"]
    assert cmd.total == 163.80
    assert cmd.substances == ["cbc", "thcx", "hpx"]


def test_commande_format_inconnu():
    cmd = commandes.lire("Merci pour votre commande de fleurs CBD", "autre-exemple.fr")
    assert cmd.substances == ["cbd"]
    assert commandes.lire("Merci pour votre commande", "autre-exemple.fr").substances == ["cbd"]


def test_filtre_sujets():
    assert commandes.est_confirmation("[Boutique] Confirmation de commande")
    assert not commandes.est_confirmation("[Boutique] Paiement accepté")
    assert not commandes.est_confirmation("Camille, c'est le moment de passer commande !")
    assert commandes.boutique_de("contact@boutique-exemple.fr") == "boutique-exemple.fr"
    assert commandes.boutique_de("moi@example.com info@autre-exemple.fr", "Votre commande") == "autre-exemple.fr"


def test_whatsapp_formats():
    lignes = [
        "12/03/2021 21:04 - Alex: t'as de la beuh ?",
        "suite du message",
        "[13/03/2021 10:00:05] Moi: on se fume un joint",
        "14/03/21, 08:15 - Alex: bonne journée",
    ]
    msgs = list(whatsapp_import.messages(lignes))
    assert len(msgs) == 3
    assert msgs[0][0] == datetime(2021, 3, 12, 21, 4)
    assert msgs[0][2].endswith("suite du message")
    assert msgs[1][1] == "Moi"
    assert msgs[2][0].year == 2021


def test_whatsapp_evenements(tmp_path):
    (tmp_path / "Discussion.txt").write_text(
        "12/03/2021 21:04 - Alex: t'as de la beuh ?\n13/03/2021 10:00 - Moi: on se fume un joint\n"
        "13/03/2021 11:00 - Moi: rien à voir\n",
        encoding="utf-8",
    )
    ev = whatsapp_import.evenements(tmp_path, ["Moi"])
    assert [(e["kind"], e["auteur"]) for e in ev] == [("achat", "autre"), ("conso", "moi")]
    assert all("texte" not in e for e in ev)  # le texte ne sort pas du PC


def test_heure_de_la_notification():
    soir = datetime(2026, 11, 22, 23, 31)
    assert push.doit_envoyer(soir, "23:30", None, repondu=False)
    assert not push.doit_envoyer(soir, "23:30", "2026-11-22", repondu=False)  # déjà envoyé
    assert not push.doit_envoyer(soir, "23:30", None, repondu=True)  # déjà renseigné
    assert not push.doit_envoyer(datetime(2026, 11, 22, 23, 29), "23:30", None, repondu=False)


def test_cles_vapid():
    cle = push.cle_publique()
    assert cle and len(cle) == 87  # point P-256 non compressé, base64url sans « = »
    assert push.cle_publique() == cle


@needs_db
def test_api_complete():
    from fastapi.testclient import TestClient

    from healthsync import conso, main, memos, store

    import asyncio

    async def prep():
        await store.init()
        await memos.init()
        await conso.init()
        async with await store.connect() as c:
            await c.execute("TRUNCATE conso_events, conso_jours, conso_reglages, conso_sources_vues, push_abonnements")

    asyncio.run(prep())
    c = TestClient(main.app)  # sans « with » : ne lance pas les boucles de fond

    e = c.get("/conso/etat").json()
    assert e["derniere_prise_thc"] is None
    assert e["reglages"]["push_heure"] == "23:30"
    assert any(s["code"] == "thcx" for s in e["catalogue"])

    il_y_a_3j = (datetime.now(timezone.utc) - timedelta(days=3, hours=2)).isoformat()
    r = c.post("/conso/prise", json={"substance": "thc", "at": il_y_a_3j})
    assert r.status_code == 201
    assert c.post("/conso/prise", json={"substance": "inconnue"}).status_code == 400

    e = c.get("/conso/etat").json()
    assert e["derniere_prise_thc"].startswith(il_y_a_3j[:16])
    assert e["en_cours"][0]["code"] == "thc"

    # Réponse du soir : CBD seulement, moral 4
    r = c.post("/conso/jour", json={"moral": 4, "niveaux": {"cbd": 2, "inconnue": 1, "thc": 0}})
    assert r.json()["niveaux"] == {"cbd": 2}
    e = c.get("/conso/etat").json()
    assert e["aujourdhui"]["repondu"] and e["aujourdhui"]["moral"] == 4
    today = e["jours"][-1]
    assert today["confiance"] == "explicite" and today["thc"] == 0 and today["niveau"] == 2

    # Notification MacroDroid : jeton obligatoire, rien gardé sans mention
    assert c.post("/ingest/notification", json={"app": "WhatsApp", "texte": "salut"}).status_code == 401
    h = {"Authorization": "Bearer jeton-de-test"}
    assert c.post("/ingest/notification", headers=h, json={"app": "WhatsApp", "texte": "salut"}).json()["retenu"] is False
    r = c.post("/ingest/notification", headers=h, json={"app": "WhatsApp", "titre": "A", "texte": "t'as de la beuh ?"}).json()
    assert r["retenu"] and r["ajoutes"] == 1
    r = c.post("/ingest/notification", headers=h, json={"app": "WhatsApp", "titre": "A", "texte": "t'as de la beuh ?"}).json()
    assert r["ajoutes"] == 0  # doublon
    assert c.post("/ingest/notification", headers=h, json={"app": "Gmail", "texte": "beuh"}).json()["retenu"] is False

    # Import WhatsApp depuis le PC : déduit, et jamais par-dessus une réponse du soir
    r = c.post("/ingest/conso", headers=h, json={"source": "whatsapp", "evenements": [
        {"at": "2021-03-12T21:04:00", "substance": "thc", "kind": "achat", "ref": "abc", "mots": ["beuh"], "auteur": "autre"},
    ]}).json()
    assert r["ajoutes"] == 1

    async def verifier():
        async with await store.connect() as conn:
            cur = await conn.execute(
                "SELECT day::date, confiance, niveau_thc FROM conso_quotidien WHERE day BETWEEN '2021-03-11' AND '2021-03-16' ORDER BY day"
            )
            rows = await cur.fetchall()
            cur = await conn.execute("SELECT count(*) FROM moral_quotidien")
            n_moral = (await cur.fetchone())[0]
        return rows, n_moral

    rows, n_moral = asyncio.run(verifier())
    conf = [r[1] for r in rows]
    # achat de rue le 12 -> 3 jours déduits (12, 13, 14), inconnu autour
    assert conf == ["inconnu", "deduit", "deduit", "deduit", "inconnu", "inconnu"]
    assert n_moral > 2000  # une ligne par jour depuis 2020

    # Réglages
    r = c.put("/conso/reglages", json={"push_heure": "22:15"}).json()
    assert r["push_heure"] == "22:15"
    assert c.put("/conso/reglages", json={"push_heure": "25:00"}).status_code == 422

    # Page et service worker servis
    assert "Ma journée" in c.get("/conso/app").text
    assert "showNotification" in c.get("/conso/sw.js").text
