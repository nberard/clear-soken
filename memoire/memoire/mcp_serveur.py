"""Serveur MCP : ta mémoire accessible depuis Claude Desktop, Claude Code, etc.

Deux façons de s'y brancher :
- stdio par SSH (aucun port ouvert) :
    ssh serveur docker exec -i memoire python -m memoire.mcp_serveur
- HTTP : https://$MEMOIRE_HOST/mcp (derrière le mot de passe Caddy)

CONFIDENTIALITÉ : tout ce que renvoie un outil MCP est lu par l'IA qui l'appelle,
donc envoyé à son fournisseur (Anthropic pour Claude). Les casquettes privées et
les conversations sensibles sont donc INVISIBLES par MCP, sauf si tu l'autorises
explicitement avec MEMOIRE_MCP_PRIVE=1.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from . import agent, config, db, importers

cfg = config.charger()
conn = db.connecter(cfg.db_path)
PRIVE_AUTORISE = os.environ.get("MEMOIRE_MCP_PRIVE") == "1"

INSTRUCTIONS = """Mémoire personnelle de l'utilisateur, construite à partir de ses conversations
passées avec ChatGPT, Claude, Gemini et Mistral, rangées par casquette (pro, perso, santé…).
Commence par `vue_ensemble` ou `profil` pour le contexte général, puis `rechercher` pour
des détails précis, et `conversation` pour relire un échange en entier. Quand une session
contient des décisions ou des faits utiles pour plus tard, propose à l'utilisateur de les
enregistrer avec `noter`."""

serveur = MCPServer("memoire", instructions=INSTRUCTIONS)


def _visible(casquette: str | None) -> bool:
    return PRIVE_AUTORISE or casquette not in cfg.privees


MASQUE = ("(résumé masqué : cette branche contient des éléments sensibles, consultable "
          "uniquement en local)")


def _resume_visible(n) -> str | None:
    """Le résumé d'un nœud, ou None s'il contient du sensible et que le privé n'est pas autorisé."""
    if n is None or not n["resume"]:
        return None
    if n["sensible"] and not PRIVE_AUTORISE:
        return MASQUE
    return n["resume"]


def _casquette_inconnue(casquette: str) -> str | None:
    if casquette not in cfg.casquettes:
        return f"Casquette inconnue. Disponibles : {', '.join(cfg.casquettes)}"
    if not _visible(casquette):
        return f"La casquette « {casquette} » est privée : elle n'est consultable qu'en local, pas par MCP."
    return None


@serveur.tool()
def casquettes() -> str:
    """Liste les casquettes (domaines de vie) de la mémoire et le nombre de conversations de chacune."""
    lignes = []
    for nom, c in cfg.casquettes.items():
        n = conn.execute("SELECT COUNT(*) FROM conv_casquettes WHERE casquette = ? AND principal = 1",
                         (nom,)).fetchone()[0]
        etat = " (privée : non consultable ici)" if not _visible(nom) else ""
        lignes.append(f"- {nom} : {c.description} — {n} conversations{etat}")
    return "\n".join(lignes)


@serveur.tool()
def vue_ensemble() -> str:
    """Vue d'ensemble courte de la vie de l'utilisateur, toutes casquettes visibles confondues."""
    nid = "racine:privee" if PRIVE_AUTORISE else "racine"
    r = conn.execute("SELECT resume, maj_le, sensible FROM noeuds WHERE id = ?", (nid,)).fetchone()
    if not r or not r["resume"]:
        return "Pas encore de vue d'ensemble : il faut importer des exports puis lancer `memoire traiter`."
    return f"{_resume_visible(r)}\n\n(mis à jour le {(r['maj_le'] or '')[:10]})"


@serveur.tool()
def profil(casquette: str) -> str:
    """Profil d'une casquette (situation, sujets en cours, tendances) et la liste de ses sujets."""
    if err := _casquette_inconnue(casquette):
        return err
    p = conn.execute("SELECT resume, sensible FROM noeuds WHERE id = ?", (f"casquette:{casquette}",)).fetchone()
    sujets = conn.execute("SELECT titre, maj_le, sensible FROM noeuds WHERE niveau = 'sujet' AND casquette = ? "
                          "ORDER BY maj_le DESC", (casquette,)).fetchall()
    texte = _resume_visible(p) or "(profil pas encore construit)"
    visibles = [s for s in sujets if PRIVE_AUTORISE or not s["sensible"]]
    if visibles:
        texte += "\n\nSujets :\n" + "\n".join(f"- {s['titre']} ({(s['maj_le'] or '')[:10]})" for s in visibles)
    if len(visibles) < len(sujets):
        texte += f"\n({len(sujets) - len(visibles)} sujet(s) sensible(s) masqué(s))"
    return texte


@serveur.tool()
def sujet(casquette: str, titre: str) -> str:
    """Résumé d'un sujet précis d'une casquette, et les conversations qui le composent."""
    if err := _casquette_inconnue(casquette):
        return err
    n = conn.execute("SELECT id, titre, resume, sensible FROM noeuds WHERE niveau = 'sujet' AND casquette = ? "
                     "AND lower(titre) = lower(?)", (casquette, titre)).fetchone()
    if not n or (n["sensible"] and not PRIVE_AUTORISE):
        return "Sujet introuvable. Utilise `profil` pour voir la liste des sujets."
    convs = conn.execute(
        """SELECT c.id, c.titre, c.source, c.cree_le, c.sensible FROM conversations c
           JOIN conv_casquettes cc ON cc.conv_id = c.id AND cc.principal = 1
           WHERE cc.casquette = ? AND lower(c.sujet) = lower(?) ORDER BY c.cree_le DESC""",
        (casquette, n["titre"])).fetchall()
    liste = "\n".join(f"- [{c['id']}] {c['titre']} ({c['source']}, {(c['cree_le'] or '')[:10]})"
                      for c in convs if PRIVE_AUTORISE or not c["sensible"])
    return f"{_resume_visible(n) or '(pas encore résumé)'}\n\nConversations :\n{liste or '(aucune visible)'}"


@serveur.tool()
def rechercher(requete: str, casquette: str | None = None, limite: int = 10) -> str:
    """Recherche plein texte dans toutes les conversations passées. Renvoie des extraits avec
    leur identifiant de conversation (à passer à `conversation` pour tout relire)."""
    if casquette and (err := _casquette_inconnue(casquette)):
        return err
    sortie = []
    for r in agent.rechercher(conn, requete, 100):
        if not PRIVE_AUTORISE and (r["sensible"] or r["casquette"] in cfg.privees):
            continue
        if casquette and r["casquette"] != casquette:
            continue
        sortie.append(f"[{r['conv_id']}] « {r['titre']} » ({r['source']}, {(r['cree_le'] or '')[:10]}, "
                      f"{r['casquette'] or 'non classée'})\n  {r['extrait']}")
        if len(sortie) >= min(limite, 30):
            break
    return "\n\n".join(sortie) or "Aucun résultat visible."


@serveur.tool()
def conversation(conv_id: str, max_caracteres: int = 20000) -> str:
    """Relit une conversation passée en entier (identifiant donné par `rechercher` ou `sujet`)."""
    c = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
    if not c:
        return "Conversation introuvable."
    cas = conn.execute("SELECT casquette FROM conv_casquettes WHERE conv_id = ? AND principal = 1",
                       (conv_id,)).fetchone()
    if not PRIVE_AUTORISE and (c["sensible"] or (cas and cas["casquette"] in cfg.privees)):
        return "Conversation sensible : consultable uniquement en local, pas par MCP."
    texte = db.texte_conversation(conn, conv_id)
    if len(texte) > max_caracteres:
        texte = texte[:max_caracteres] + "\n\n[…tronqué, augmente max_caracteres pour la suite…]"
    entete = f"« {c['titre']} » — {c['source']}, {(c['cree_le'] or '')[:10]}"
    if c["resume"]:
        entete += f"\nRésumé : {c['resume']}"
    return f"{entete}\n\n{texte}"


@serveur.tool()
def noter(titre: str, contenu: str) -> str:
    """Enregistre dans la mémoire un résumé de la session en cours (faits, décisions, à faire).
    Il sera classé dans une casquette au prochain traitement, avec le même filtre de
    confidentialité que les imports. À utiliser avec l'accord de l'utilisateur."""
    if not contenu.strip():
        return "Contenu vide : rien n'a été enregistré."
    maintenant = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ext_id = hashlib.sha256(f"{maintenant}{titre}{contenu}".encode()).hexdigest()[:16]
    conv = importers.Conv("mcp", ext_id, titre.strip() or "Note de session", maintenant, maintenant,
                          [importers.Msg("user", contenu.strip(), maintenant)])
    importers.enregistrer(conn, [conv])
    return f"Noté ({conv.id}). Ce sera classé et intégré à l'arbre au prochain `memoire traiter`."


def app_http():
    """Application ASGI streamable HTTP (route /mcp), montée dans l'interface web.
    Sa durée de vie (session_manager.run) est gérée par l'appli web."""
    hotes = [h for h in (os.environ.get("MEMOIRE_HOST"), "memoire:8770", "localhost:8770", "127.0.0.1:8770") if h]
    return serveur.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        transport_security=TransportSecuritySettings(allowed_hosts=hotes, allowed_origins=[]),
    )


if __name__ == "__main__":
    serveur.run("stdio")
