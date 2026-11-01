"""Petite interface web. Le mot de passe est géré par Caddy (basic_auth),
comme pour mint-health : le conteneur n'est joignable que par le réseau « proxy »."""
from __future__ import annotations

import tempfile
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import agent, config, db, importers, llm, pipeline

cfg = config.charger()
conn = db.connecter(cfg.db_path)
api_llm, local_llm = llm.construire(cfg)
verrou = threading.Lock()  # un seul traitement à la fois (SQLite + petit serveur)
app = FastAPI(title="Mémoire", docs_url=None, redoc_url=None)


class Question(BaseModel):
    question: str
    casquettes: list[str] | None = None


@app.get("/api/etat")
def etat():
    rows = conn.execute("SELECT statut, COUNT(*) n FROM conversations GROUP BY statut").fetchall()
    return {"conversations": {r["statut"]: r["n"] for r in rows},
            "casquettes": {n: {"prive": c.prive, "description": c.description} for n, c in cfg.casquettes.items()}}


@app.get("/api/arbre")
def arbre():
    return [dict(r) for r in conn.execute(
        "SELECT id, niveau, casquette, titre, resume, a_refaire, maj_le FROM noeuds ORDER BY id")]


@app.post("/api/demander")
def demander(q: Question):
    r = agent.demander(conn, cfg, q.question, api_llm, local_llm, q.casquettes)
    return {"reponse": r.texte, "casquettes": r.casquettes, "modele": r.backend, "sources": r.sources}


@app.post("/api/importer")
async def importer(fichier: UploadFile, source: str | None = None):
    suffixe = Path(fichier.filename or "").suffix or ".json"
    with tempfile.NamedTemporaryFile(suffix=suffixe) as tmp:
        while bloc := await fichier.read(1 << 20):
            tmp.write(bloc)
        tmp.flush()
        convs = importers.lire_fichier(tmp.name, source)
    if not convs:
        raise HTTPException(400, "Format non reconnu ou export vide")
    return importers.enregistrer(conn, convs)


@app.post("/api/traiter")
def traiter(limite: int | None = None):
    if not verrou.acquire(blocking=False):
        raise HTTPException(409, "Un traitement est déjà en cours")

    def tache():
        try:
            pipeline.traiter_tout(conn, cfg, api_llm, local_llm, limite)
        finally:
            verrou.release()

    threading.Thread(target=tache, daemon=True).start()
    return {"lance": True}


PAGE = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Mémoire</title>
<style>
:root{--bg:#f7f6f2;--fg:#1d1d1b;--carte:#fff;--trait:#ddd;--accent:#3d6b5a}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#eceae4;--carte:#222220;--trait:#3a3a37;--accent:#7fb8a2}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}
main{max-width:720px;margin:auto;padding:16px}
textarea,select,button,input{font:inherit;width:100%;box-sizing:border-box;margin:6px 0;padding:10px;
 border:1px solid var(--trait);border-radius:10px;background:var(--carte);color:var(--fg)}
button{background:var(--accent);color:#fff;border:0;cursor:pointer}
.carte{background:var(--carte);border:1px solid var(--trait);border-radius:12px;padding:12px;margin:12px 0;white-space:pre-wrap}
small{opacity:.7} details{margin:4px 0} summary{cursor:pointer}
</style></head><body><main>
<h1>Mémoire</h1>
<textarea id="q" rows="3" placeholder="Pose une question à ta mémoire…"></textarea>
<select id="c"><option value="">Casquette : automatique</option></select>
<button onclick="demander()">Demander</button>
<div id="r"></div>
<h2>Arbre</h2><div id="arbre"><small>Chargement…</small></div>
<h2>Importer un export</h2>
<input type="file" id="f" accept=".json,.zip"><button onclick="importer()">Importer puis traiter</button>
<div id="i"></div><p><small id="etat"></small></p>
</main><script>
const $=id=>document.getElementById(id), esc=s=>(s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
async function etat(){const e=await (await fetch('api/etat')).json();
 $('etat').textContent='Conversations : '+JSON.stringify(e.conversations);
 if($('c').options.length==1)for(const[n,c]of Object.entries(e.casquettes))$('c').add(new Option(n+(c.prive?' 🔒':''),n));}
async function arbre(){const n=await (await fetch('api/arbre')).json(), h=[];
 for(const x of n){const p=x.niveau=='sujet'?'— ':x.niveau=='casquette'?'':'★ ';
  h.push('<details><summary>'+p+esc(x.titre)+(x.a_refaire?' <small>(à refaire)</small>':'')+'</summary><div class="carte">'+esc(x.resume||'—')+'</div></details>');}
 $('arbre').innerHTML=h.join('')||'<small>Vide : importe un export.</small>';}
async function demander(){$('r').innerHTML='<div class="carte">…</div>';
 const c=$('c').value, r=await (await fetch('api/demander',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({question:$('q').value,casquettes:c?[c]:null})})).json();
 $('r').innerHTML='<div class="carte">'+esc(r.reponse)+'\\n\\n<small>'+esc(r.casquettes.join(', '))+' · '+esc(r.modele)+'</small></div>';}
async function importer(){const f=$('f').files[0]; if(!f)return; const d=new FormData(); d.append('fichier',f);
 const r=await fetch('api/importer',{method:'POST',body:d}); $('i').textContent=JSON.stringify(await r.json());
 if(r.ok){await fetch('api/traiter',{method:'POST'}); $('i').textContent+=' — traitement lancé';}}
etat(); arbre();
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def page():
    return PAGE
