# Mémoire — un agent qui te connaît, casquette par casquette

Mémoire rassemble tes conversations avec **ChatGPT, Claude, Gemini et Mistral (Le Chat)** et les range dans un **arbre de contexte** par casquette : pro, perso, santé physique, santé mentale… Tu peux ensuite lui poser des questions sur toi-même : « où j'en suis sur clear-soken ? », « est-ce que mes angoisses du soir vont mieux ? ».

> Outil **personnel**, séparé de l'appli patients Clear Soken : autre conteneur, autre base, aucune donnée commune.

## L'arbre de contexte

```
racine                   vue d'ensemble (sans les casquettes privées)   → API
racine:privee            vue transverse, liens entre domaines           → local
├── casquette:pro        profil de la casquette
│   ├── sujet:pro:clear-soken      résumé d'un sujet
│   │   ├── conversation ChatGPT 12/10   (résumé + messages bruts)
│   │   └── conversation Claude 28/10
│   └── …
└── casquette:sante_mentale  🔒
    └── …   + liens croisés vers d'autres casquettes
```

Pour répondre, l'agent lit la racine, puis les profils des casquettes concernées, puis les sujets, et enfin les passages exacts trouvés par recherche plein texte. Chaque casquette a sa part du contexte, pour qu'aucune n'écrase les autres. Un nouvel import ne refait que les branches touchées.

## Confidentialité : le mode hybride

| | Traité par |
|---|---|
| pro, perso, santé physique | API (Mistral par défaut, hébergé en France, ou Claude) |
| santé mentale (`prive = true`) | **modèle local** (Ollama sur ton PC), jamais l'API |

- **Avant tout envoi**, chaque conversation est passée au crible des mots-clés des casquettes privées (`casquettes.toml`). Si elle en contient, elle est traitée **uniquement** en local et rangée sous la casquette privée ; sa casquette d'origine reste un lien croisé.
- Le filtre est **volontairement large** : une conversation de travail qui parle de « stress » ou d'« hospitalisation » partira en local. Les conversations sur clear-soken lui-même (psychiatrie, addictions…) seront donc souvent traitées en local. C'est le prix de la prudence ; ajuste les mots-clés si besoin.
- Une question qui touche une casquette privée est traitée **entièrement** en local, et les passages sensibles ne sont jamais ajoutés à une question envoyée à l'API.
- **PC éteint ?** Les conversations sensibles attendent (`en_attente_local`) et seront traitées au prochain `traiter`. Rien ne bascule vers l'API.
- Le stockage (SQLite) reste sur ton serveur. Caddy protège l'accès par mot de passe et ne garde pas de journal.

## Récupérer tes exports

| Service | Où | Fichier |
|---|---|---|
| ChatGPT | Paramètres → Contrôle des données → Exporter | zip avec `conversations.json` |
| Claude | Paramètres → Confidentialité → Exporter les données | zip avec `conversations.json` |
| Gemini | [takeout.google.com](https://takeout.google.com) → « Mon activité » → **Applications Gemini**, format **JSON** | zip avec `MyActivity.json` |
| Mistral | Le Chat → Paramètres → exporter | json (format générique, à ajuster sur un vrai export) |

Le zip s'importe tel quel. Gemini n'exporte pas de conversations, seulement des questions/réponses : elles sont regroupées par jour. Ré-importer un export plus récent ne retraite que les conversations nouvelles ou modifiées.

## Installer sur le serveur

```bash
cd memoire && cp .env.example .env && nano .env   # clé Mistral ou Anthropic
cd .. && make memoire-deploy

# Accès web : dans proxy/.env, ajoute MEMOIRE_HOST (ex. memoire.touplitoui.me),
# MEMOIRE_AUTH_USER et MEMOIRE_AUTH_HASH (docker exec caddy caddy hash-password)
make memoire-proxy
```

Le conteneur est limité à 300 Mo de RAM : il ne fait que stocker et appeler des modèles, le serveur (Atom, 4 Go) ne fait tourner aucun LLM.

### Le modèle local sur ton PC

```bash
# Sur ton PC (avec une carte graphique de préférence)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:7b

# Tunnel : le serveur joint l'Ollama de ton PC tant que cette commande tourne.
# Sur le serveur, une fois : GatewayPorts clientspecified dans /etc/ssh/sshd_config
ssh -N -R 172.17.0.1:11434:localhost:11434 utilisateur@5.39.76.84
```

`172.17.0.1` est l'adresse de l'hôte vue depuis Docker (`OLLAMA_URL` dans `.env`). Le port n'est ouvert que sur le réseau Docker interne, pas sur Internet. Alternative plus simple si tu l'utilises déjà : Tailscale, avec `OLLAMA_URL=http://<ip-tailscale-du-pc>:11434`.

## Utiliser

```bash
make memoire-import FICHIER=~/Téléchargements/chatgpt-export.zip
make memoire-import FICHIER=~/Téléchargements/claude-export.zip
make memoire-traiter              # classe, résume, construit l'arbre (allume le tunnel avant)

docker exec memoire python -m memoire demander "Où j'en suis sur clear-soken ?"
docker exec memoire python -m memoire demander "Comment va mon sommeil ?" --casquette sante_physique
docker exec memoire python -m memoire arbre
docker exec memoire python -m memoire etat
```

Ou depuis le navigateur sur `https://$MEMOIRE_HOST` : question, arbre dépliable, import d'un export.

**Coût** : l'import initial est la partie chère (un appel par conversation, plus les résumés de l'arbre). Avec `mistral-small`, quelques milliers de conversations coûtent de l'ordre de quelques euros. Ensuite, chaque question = un appel. Commence par `python -m memoire traiter --limite 50` pour vérifier le tri.

## Développer

```bash
cd memoire
pip install -r requirements.txt pytest
python -m pytest tests          # faux LLM : aucun appel réseau
MEMOIRE_DB=./data/memoire.db uvicorn memoire.web:app --port 8770
```

| Fichier | Rôle |
|---|---|
| `casquettes.toml` | les casquettes, leur caractère privé, leurs mots-clés |
| `memoire/importers.py` | lecture des exports ChatGPT, Claude, Gemini, Mistral |
| `memoire/sensible.py` | repérage des contenus sensibles avant envoi |
| `memoire/pipeline.py` | classement, résumés, construction de l'arbre |
| `memoire/agent.py` | routage d'une question et assemblage du contexte |
| `memoire/llm.py` | backends Mistral, Claude, Ollama |
| `memoire/web.py` | interface web et API |

## Prochaines étapes

- Serveur **MCP** pour interroger ta mémoire directement depuis Claude Desktop / Claude Code.
- Source **mint-health** (sommeil, pas, journal vocal) pour la casquette santé physique.
- Recherche par le sens (embeddings) en plus de la recherche plein texte.
- Correction manuelle d'un classement depuis l'interface.
