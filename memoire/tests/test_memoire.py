import json
import zipfile

import pytest

from memoire import agent, config, db, importers, pipeline
from memoire.llm import Indisponible

CHATGPT = [{
    "id": "g1", "title": "Déployer Caddy", "create_time": 1730000000, "update_time": 1730000100,
    "current_node": "c",
    "mapping": {
        "a": {"message": None, "parent": None},
        "b": {"parent": "a", "message": {"author": {"role": "user"}, "create_time": 1730000000,
                                         "content": {"parts": ["Comment configurer Caddy sur mon serveur docker ?"]}}},
        "x": {"parent": "b", "message": {"author": {"role": "assistant"}, "content": {"parts": ["brouillon abandonné"]}}},
        "c": {"parent": "b", "message": {"author": {"role": "assistant"}, "create_time": 1730000050,
                                         "content": {"parts": ["Utilise un reverse_proxy."]}}},
    },
}]

CLAUDE = [{
    "uuid": "k1", "name": "Nuits difficiles", "created_at": "2026-10-01T10:00:00Z", "updated_at": "2026-10-01T11:00:00Z",
    "chat_messages": [
        {"sender": "human", "text": "J'ai beaucoup d'angoisse le soir, je n'arrive pas à me calmer.",
         "created_at": "2026-10-01T10:00:00Z"},
        {"sender": "assistant", "text": "", "content": [{"type": "text", "text": "Essayons la cohérence cardiaque."}]},
    ],
}]

GEMINI = [
    {"header": "Gemini Apps", "title": "Prompted idée de cadeau pour ma sœur", "time": "2026-09-01T09:00:00Z",
     "safeHtmlItem": [{"html": "<p>Un livre &amp; des fleurs</p>"}]},
    {"header": "Gemini Apps", "title": "Prompted et pour mon père ?", "time": "2026-09-01T09:05:00Z"},
]

MISTRAL = {"conversations": [{"id": "m1", "title": "Budget", "messages": [
    {"role": "user", "content": "Aide-moi à faire mon budget du mois"},
    {"role": "assistant", "content": [{"type": "text", "text": "D'accord."}]}]}]}


class Faux:
    """Faux LLM : enregistre tout ce qu'il reçoit."""

    def __init__(self, nom, local, casquette="pro", panne=False):
        self.nom, self.local, self.max_chars = nom, local, 50_000
        self.casquette, self.panne, self.recu = casquette, panne, []

    def completer(self, system, prompt, json_mode=False):
        if self.panne:
            raise Indisponible("éteint")
        self.recu.append(prompt)
        if json_mode:
            return json.dumps({"casquette": self.casquette, "autres_casquettes": [],
                               "sujet": "Sujet test", "resume": f"résumé par {self.nom}"})
        return f"synthèse {self.nom}"


@pytest.fixture
def cfg(tmp_path):
    c = config.charger()
    c.db_path = ":memory:"
    return c


@pytest.fixture
def conn(cfg):
    return db.connecter(":memory:")


def test_formats_detectes():
    g = importers.lire_donnees(CHATGPT)
    assert g[0].source == "chatgpt" and [m.contenu for m in g[0].messages] == [
        "Comment configurer Caddy sur mon serveur docker ?", "Utilise un reverse_proxy."]  # pas le brouillon
    k = importers.lire_donnees(CLAUDE)
    assert k[0].source == "claude" and k[0].messages[0].role == "user"
    assert k[0].messages[1].contenu == "Essayons la cohérence cardiaque."
    ge = importers.lire_donnees(GEMINI)
    assert len(ge) == 1 and ge[0].messages[0].contenu == "idée de cadeau pour ma sœur"
    assert ge[0].messages[1].contenu == "Un livre & des fleurs"
    mi = importers.lire_donnees(MISTRAL)
    assert mi[0].source == "mistral" and mi[0].messages[1].contenu == "D'accord."


def test_zip_et_reimport(tmp_path, conn):
    z = tmp_path / "export.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("conversations.json", json.dumps(CLAUDE))
    convs = importers.lire_fichier(z)
    assert importers.enregistrer(conn, convs)["nouvelles"] == 1
    assert importers.enregistrer(conn, convs)["inchangees"] == 1
    CLAUDE2 = json.loads(json.dumps(CLAUDE))
    CLAUDE2[0]["chat_messages"].append({"sender": "human", "text": "Merci"})
    assert importers.enregistrer(conn, importers.lire_donnees(CLAUDE2))["modifiees"] == 1


def _tout_importer(conn):
    for d in (CHATGPT, CLAUDE, GEMINI, MISTRAL):
        importers.enregistrer(conn, importers.lire_donnees(d))


def test_sensible_traite_en_local_uniquement(conn, cfg):
    _tout_importer(conn)
    api, local = Faux("api", False, "pro"), Faux("local", True, "sante_mentale")
    pipeline.traiter_tout(conn, cfg, api, local)
    # Aucun prompt envoyé à l'API ne contient la conversation sur l'angoisse.
    assert not any("angoisse" in p for p in api.recu)
    assert any("angoisse" in p for p in local.recu)
    c = conn.execute("SELECT sensible, statut FROM conversations WHERE id='claude:k1'").fetchone()
    assert c["sensible"] == 1 and c["statut"] == "traite"
    # La racine API ne contient pas le profil santé mentale.
    assert not any("résumé par local" in p for p in api.recu)
    noeuds = {r["id"] for r in conn.execute("SELECT id FROM noeuds WHERE a_refaire = 0")}
    assert {"racine", "racine:privee", "casquette:sante_mentale", "casquette:pro"} <= noeuds


def test_sensible_range_sous_casquette_privee(conn, cfg):
    """Même si le modèle la classe « pro », une conversation sensible part sous santé mentale."""
    _tout_importer(conn)
    api, local = Faux("api", False, "pro"), Faux("local", True, "pro")
    pipeline.traiter_tout(conn, cfg, api, local)
    cc = {r["casquette"]: r["principal"] for r in
          conn.execute("SELECT * FROM conv_casquettes WHERE conv_id='claude:k1'")}
    assert cc == {"sante_mentale": 1, "pro": 0}


def test_local_eteint_met_en_attente(conn, cfg):
    _tout_importer(conn)
    api, local = Faux("api", False), Faux("local", True, panne=True)
    stats = pipeline.traiter_tout(conn, cfg, api, local)
    assert stats["en_attente_local"] == 1
    assert not any("angoisse" in p for p in api.recu)
    # Le PC se rallume : la conversation est reprise.
    local.panne = False
    local.casquette = "sante_mentale"
    pipeline.traiter_tout(conn, cfg, api, local)
    assert conn.execute("SELECT statut FROM conversations WHERE id='claude:k1'").fetchone()[0] == "traite"


def test_agent_route_et_protege(conn, cfg):
    _tout_importer(conn)
    api, local = Faux("api", False, "pro"), Faux("local", True, "sante_mentale")
    pipeline.traiter_tout(conn, cfg, api, local)
    api.recu.clear(), local.recu.clear()

    r = agent.demander(conn, cfg, "Comment j'ai configuré Caddy sur le serveur ?", api, local)
    assert r.backend == "api" and "pro" in r.casquettes
    assert any("reverse_proxy" in p for p in api.recu)
    assert not any("angoisse" in p for p in api.recu)

    r = agent.demander(conn, cfg, "Est-ce que mon angoisse du soir va mieux ?", api, local)
    assert r.backend == "local" and "sante_mentale" in r.casquettes
    assert any("angoisse" in p for p in local.recu)


def test_agent_local_eteint(conn, cfg):
    api, local = Faux("api", False), Faux("local", True, panne=True)
    r = agent.demander(conn, cfg, "mon anxiété", api, local)
    assert "modèle local ne répond pas" in r.texte and not api.recu


def test_api_injoignable_reste_nouveau(conn, cfg):
    _tout_importer(conn)
    api, local = Faux("api", False, panne=True), Faux("local", True, "sante_mentale")
    stats = pipeline.traiter_tout(conn, cfg, api, local)
    assert stats["api_injoignable"] == 3
    assert conn.execute("SELECT statut FROM conversations WHERE id='chatgpt:g1'").fetchone()[0] == "nouveau"


def test_export_claude_multi_zips(tmp_path, conn):
    """Nouvel export claude.ai : un zip par catégorie (conversations, memories, projects)."""
    memoires = {"account_uuid": "a", "memory_files": [
        {"path": "/memories/travail.md", "content": "Nico développe clear-soken.", "updated_at": "2026-11-01T10:00:00Z"},
        {"path": "/memories/vide.md", "content": "  ", "updated_at": "2026-11-01T10:00:00Z"}]}
    projet = {"uuid": "p1", "name": "Clear Soken", "description": "Appli PWA", "prompt_template": "Réponds en français",
              "is_private": True, "created_at": "2026-10-01T10:00:00Z", "updated_at": "2026-10-02T10:00:00Z", "docs": []}
    vide = {"uuid": "p2", "name": "Vide", "description": "", "prompt_template": "", "docs": []}
    fichiers = {"conversations-000.zip": {"conversations.json": CLAUDE},
                "memories-000.zip": {"memories/x.json": memoires},
                "projects-000.zip": {"projects/p1.json": projet, "projects/p2.json": vide}}
    convs = []
    for nom, contenu in fichiers.items():
        with zipfile.ZipFile(tmp_path / nom, "w") as z:
            for n, d in contenu.items():
                z.writestr(n, json.dumps(d))
        convs += importers.lire_fichier(tmp_path / nom)
    ids = {c.id for c in convs}
    assert ids == {"claude:k1", "claude_memoire:/memories/travail.md", "claude_projet:p1"}
    p = next(c for c in convs if c.id == "claude_projet:p1")
    assert p.titre == "Projet Claude : Clear Soken" and "Réponds en français" in p.messages[0].contenu
    assert importers.enregistrer(conn, convs)["nouvelles"] == 3


def test_ollama_injoignable_echoue_vite():
    """Un Ollama injoignable ne doit pas bloquer : échec rapide, puis plus d'essai pendant 60 s."""
    import time
    from memoire.llm import Ollama
    o = Ollama("http://10.255.255.1:11434", "x")  # adresse non routable : la connexion ne répond jamais
    t = time.monotonic()
    with pytest.raises(Indisponible):
        o.completer("s", "p")
    assert time.monotonic() - t < 15
    t = time.monotonic()
    with pytest.raises(Indisponible):
        o.completer("s", "p")
    assert time.monotonic() - t < 0.1


def test_cle_manquante_message_clair(cfg, capsys, monkeypatch):
    from memoire import __main__ as cli, llm
    cfg.api, cfg.mistral_key = "mistral", ""
    with pytest.raises(llm.CleManquante, match="MISTRAL_API_KEY"):
        llm.construire(cfg)
    monkeypatch.setenv("MEMOIRE_API", "mistral")
    monkeypatch.setenv("MISTRAL_API_KEY", "")
    monkeypatch.setenv("MEMOIRE_DB", ":memory:")
    assert cli.main(["traiter"]) == 1
    assert "MISTRAL_API_KEY est vide" in capsys.readouterr().err


def test_mode_tout_local(conn, cfg):
    from memoire import llm
    cfg.api, cfg.mistral_key = "ollama", ""
    api, local = llm.construire(cfg)  # pas de clé exigée
    assert api is local and local.local
    # Le PC éteint : tout attend en local, rien n'est perdu.
    local.completer = lambda *a, **k: (_ for _ in ()).throw(Indisponible("éteint"))
    _tout_importer(conn)
    stats = pipeline.traiter_tout(conn, cfg, api, local)
    assert stats == {"en_attente_local": 4, "noeuds_refaits": 0, "noeuds_en_attente_local": 0}


def test_tout_local_garde_le_classement_du_modele(conn, cfg):
    """En mode tout local, une conversation sensible reste dans la casquette choisie par le modèle,
    mais sa branche est marquée sensible."""
    _tout_importer(conn)
    loc = Faux("local", True, "sante_physique")
    pipeline.traiter_tout(conn, cfg, loc, loc)
    cc = conn.execute("SELECT casquette FROM conv_casquettes WHERE conv_id='claude:k1' AND principal=1").fetchone()
    assert cc[0] == "sante_physique"
    assert conn.execute("SELECT sensible FROM noeuds WHERE id='casquette:sante_physique'").fetchone()[0] == 1


def test_traiter_tout_reclasse(conn, cfg):
    _tout_importer(conn)
    loc = Faux("local", True, "pro")
    pipeline.traiter_tout(conn, cfg, loc, loc)
    n = len(loc.recu)
    stats = pipeline.traiter_tout(conn, cfg, loc, loc, tout=True)
    assert stats["traite"] == 4 and len(loc.recu) > n


def test_migration_noeuds_sensible(tmp_path):
    import sqlite3
    p = tmp_path / "ancienne.db"
    old = sqlite3.connect(p)
    old.execute("CREATE TABLE noeuds (id TEXT PRIMARY KEY, niveau TEXT NOT NULL, casquette TEXT, titre TEXT, "
                "resume TEXT, a_refaire INTEGER NOT NULL DEFAULT 1, maj_le TEXT)")
    old.execute("INSERT INTO noeuds (id, niveau, a_refaire) VALUES ('racine', 'racine', 0)")
    old.commit(); old.close()
    c = db.connecter(str(p))
    r = c.execute("SELECT sensible, a_refaire FROM noeuds WHERE id='racine'").fetchone()
    assert tuple(r) == (0, 1)


def test_schema_et_exemples_dans_la_consigne(conn, cfg):
    _tout_importer(conn)
    loc = Faux("local", True, "pro")
    vus = []
    orig = loc.completer
    loc.completer = lambda s, p, json_mode=False: (vus.append(json_mode), orig(s, p, json_mode))[1]
    pipeline.traiter_tout(conn, cfg, loc, loc)
    schema = next(j for j in vus if isinstance(j, dict))
    assert set(schema["properties"]["casquette"]["enum"]) == set(cfg.casquettes)
    assert any("Résilier mon abonnement Free" in p for p in loc.recu)


def test_casquette_hors_liste_repli_mots_cles(conn, cfg):
    _tout_importer(conn)
    loc = Faux("local", True, "inexistante")
    pipeline.traiter_tout(conn, cfg, loc, loc)
    # « Comment configurer Caddy sur mon serveur docker » : mots-clés pro
    cc = conn.execute("SELECT casquette FROM conv_casquettes WHERE conv_id='chatgpt:g1' AND principal=1").fetchone()
    assert cc[0] == "pro"


def test_reclasser(conn, cfg, capsys, monkeypatch, tmp_path):
    _tout_importer(conn)
    loc = Faux("local", True, "sante_physique")
    pipeline.traiter_tout(conn, cfg, loc, loc)
    pipeline.reclasser(conn, cfg, "gemini:2026-09-01", "perso")
    cc = {r[0]: r[1] for r in conn.execute("SELECT casquette, principal FROM conv_casquettes WHERE conv_id='gemini:2026-09-01'")}
    assert cc == {"perso": 1}
    assert conn.execute("SELECT a_refaire FROM noeuds WHERE id='casquette:perso'").fetchone()[0] == 1
    with pytest.raises(ValueError):
        pipeline.reclasser(conn, cfg, "gemini:2026-09-01", "nimporte")
