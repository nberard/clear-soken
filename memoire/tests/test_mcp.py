import asyncio

import pytest
from mcp import Client

from memoire import config, db, importers, mcp_serveur, pipeline

from test_memoire import CHATGPT, CLAUDE, Faux


@pytest.fixture
def memoire(monkeypatch):
    """Mémoire remplie : une conversation pro (Caddy) et une sensible (angoisse)."""
    conn = db.connecter(":memory:")
    cfg = config.charger()
    for d in (CHATGPT, CLAUDE):
        importers.enregistrer(conn, importers.lire_donnees(d))
    pipeline.traiter_tout(conn, cfg, Faux("api", False, "pro"), Faux("local", True, "sante_mentale"))
    monkeypatch.setattr(mcp_serveur, "conn", conn)
    monkeypatch.setattr(mcp_serveur, "PRIVE_AUTORISE", False)
    return conn


def appeler(outil, **args):
    async def go():
        async with Client(mcp_serveur.serveur) as c:
            r = await c.call_tool(outil, args)
            return "".join(b.text for b in r.content if hasattr(b, "text"))
    return asyncio.run(go())


def test_outils_exposes():
    async def go():
        async with Client(mcp_serveur.serveur) as c:
            return {t.name for t in (await c.list_tools()).tools}
    assert asyncio.run(go()) == {"casquettes", "vue_ensemble", "profil", "sujet",
                                 "rechercher", "conversation", "noter"}


def test_recherche_et_lecture(memoire):
    r = appeler("rechercher", requete="caddy serveur")
    assert "chatgpt:g1" in r
    assert "reverse_proxy" in appeler("conversation", conv_id="chatgpt:g1")
    assert "Sujet test" in appeler("profil", casquette="pro")


def test_prive_invisible_par_defaut(memoire):
    assert "angoisse" not in appeler("rechercher", requete="angoisse soir")
    assert "sensible" in appeler("conversation", conv_id="claude:k1")
    assert "privée" in appeler("profil", casquette="sante_mentale")
    assert "privée" in appeler("sujet", casquette="sante_mentale", titre="Sujet test")
    assert "résumé par local" not in appeler("vue_ensemble")


def test_prive_sur_autorisation(memoire, monkeypatch):
    monkeypatch.setattr(mcp_serveur, "PRIVE_AUTORISE", True)
    assert "claude:k1" in appeler("rechercher", requete="angoisse soir")
    assert "angoisse" in appeler("conversation", conv_id="claude:k1")


def test_noter(memoire):
    r = appeler("noter", titre="Choix de Mistral", contenu="On a choisi Mistral pour l'API.")
    assert "Noté" in r
    row = memoire.execute("SELECT source, statut FROM conversations WHERE titre = 'Choix de Mistral'").fetchone()
    assert tuple(row) == ("mcp", "nouveau")
