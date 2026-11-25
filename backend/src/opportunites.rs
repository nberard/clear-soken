//! Espace admin : opportunités pro tirées de ma boîte Gmail (contacts de recruteurs, alertes d'offres, démarches).
//!
//! Le serveur ne lit pas Gmail : seule une session Claude reliée à Gmail y a accès. Elle relève les mails (sujet,
//! expéditeur, date, court extrait) et les envoie ici. Le classement (recruteur, offre sérieuse, alerte, démarche),
//! la localisation et la fraîcheur sont déduits dans le navigateur (frontend/src/lib/opportunites.ts), pour pouvoir
//! les corriger sans réimporter.
//! - `POST /api/admin/opportunites/import` (Authorization: Bearer OPPORTUNITES_JETON, sinon CLAUDE_INDEX_JETON)
//!   remplace le relevé ;
//! - `GET /api/admin/opportunites` renvoie { releve, suivi } aux comptes connectés à l'espace admin ;
//! - `POST /api/admin/opportunites/suivi` pose mon statut sur un mail (à creuser, contacté, écarté…) et une note.
//!
//! Relevé et suivi sont gardés dans des fichiers à côté des comptes (volume « comptes ») : ils contiennent des noms
//! de recruteurs et des extraits de mails, ils ne doivent jamais aller dans git.

use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
    sync::Mutex,
};

use axum::{
    Json, Router,
    extract::{DefaultBodyLimit, State},
    http::{HeaderMap, StatusCode, header},
    response::{IntoResponse, Response},
    routing::{get, post},
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::{AppState, verdicts::aujourdhui};

const TAILLE_MAX: usize = 8 * 1024 * 1024;
pub const STATUTS: &[&str] = &["a_creuser", "contacte", "entretien", "ecarte", "archive"];
const NOTE_MAX: usize = 2000;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Suivi {
    pub statut: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub note: String,
    /// Date du dernier changement (AAAA-MM-JJ)
    pub le: String,
}

pub struct Opportunites {
    releve: PathBuf,
    suivi_fichier: PathBuf,
    suivi: Mutex<BTreeMap<String, Suivi>>,
    jeton: Option<String>,
}

impl Opportunites {
    pub fn new(releve: PathBuf, jeton: Option<String>) -> Self {
        let suivi_fichier = releve.with_file_name("opportunites_suivi.json");
        let suivi = std::fs::read_to_string(&suivi_fichier)
            .ok()
            .and_then(|raw| serde_json::from_str(&raw).ok())
            .unwrap_or_default();
        Self { releve, suivi_fichier, suivi: Mutex::new(suivi), jeton: jeton.filter(|j| j.len() >= 32) }
    }

    pub fn depuis_env() -> Self {
        let env = |k: &str| std::env::var(k).ok().filter(|v| !v.trim().is_empty());
        let releve = env("OPPORTUNITES_FILE").map(PathBuf::from).unwrap_or_else(|| {
            PathBuf::from(env("COMPTES_FILE").unwrap_or_else(|| "comptes/comptes.json".into()))
                .with_file_name("opportunites.json")
        });
        Self::new(releve, env("OPPORTUNITES_JETON").or_else(|| env("CLAUDE_INDEX_JETON")))
    }

    pub fn import_ouvert(&self) -> bool {
        self.jeton.is_some()
    }

    fn poser(&self, id: &str, statut: Option<&str>, note: &str) -> Result<(), String> {
        let mut s = self.suivi.lock().unwrap();
        match statut {
            Some(st) => {
                s.insert(id.to_owned(), Suivi { statut: st.to_owned(), note: note.to_owned(), le: aujourdhui() });
            }
            None => {
                s.remove(id);
            }
        }
        ecrire(&self.suivi_fichier, &serde_json::to_vec_pretty(&*s).expect("sérialisation du suivi"))
    }
}

/// Écriture atomique (fichier temporaire puis renommage), lisible par l'appli seulement
fn ecrire(path: &Path, octets: &[u8]) -> Result<(), String> {
    use std::io::Write;
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir).map_err(|e| e.to_string())?;
    }
    let tmp = path.with_extension("json.tmp");
    let mut options = std::fs::OpenOptions::new();
    options.write(true).create(true).truncate(true);
    #[cfg(unix)]
    std::os::unix::fs::OpenOptionsExt::mode(&mut options, 0o600);
    options
        .open(&tmp)
        .and_then(|mut f| f.write_all(octets).and_then(|_| f.sync_all()))
        .and_then(|_| std::fs::rename(&tmp, path))
        .map_err(|e| format!("écriture de {} impossible : {e}", path.display()))
}

/// Identifiant de fil Gmail : hexadécimal, 20 caractères au plus
fn id_valide(id: &str) -> bool {
    !id.is_empty() && id.len() <= 20 && id.chars().all(|c| c.is_ascii_hexdigit())
}

/// Forme minimale attendue : { genere_le, mails: [ { id, le, sujet, expediteur, … } ] }
fn releve_valide(v: &Value) -> bool {
    v.get("mails").and_then(Value::as_array).is_some_and(|m| {
        m.iter().all(|x| {
            x.get("id").and_then(Value::as_str).is_some_and(id_valide)
                && x.get("sujet").is_some_and(Value::is_string)
                && x.get("expediteur").is_some_and(Value::is_string)
                && x.get("le").is_some_and(Value::is_string)
        })
    })
}

fn egal_temps_constant(a: &[u8], b: &[u8]) -> bool {
    a.len() == b.len() && a.iter().zip(b).fold(0u8, |acc, (x, y)| acc | (x ^ y)) == 0
}

fn connecte(state: &AppState, headers: &HeaderMap) -> Result<(), StatusCode> {
    let a = state.admin.as_ref().ok_or(StatusCode::NOT_FOUND)?;
    a.session(headers).map(|_| ()).ok_or(StatusCode::UNAUTHORIZED)
}

/// `GET /api/admin/opportunites` : { releve, suivi } ; releve vaut { mails: [] } tant que rien n'a été importé
async fn lire(State(state): State<AppState>, headers: HeaderMap) -> Response {
    if let Err(code) = connecte(&state, &headers) {
        return code.into_response();
    }
    let o = &state.opportunites;
    let releve: Value = match tokio::fs::read(&o.releve).await {
        Ok(octets) => serde_json::from_slice(&octets).unwrap_or_else(|_| json!({ "mails": [] })),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => json!({ "genere_le": null, "mails": [] }),
        Err(e) => {
            tracing::error!("relevé des opportunités : {e}");
            return StatusCode::INTERNAL_SERVER_ERROR.into_response();
        }
    };
    let suivi = o.suivi.lock().unwrap().clone();
    Json(json!({ "releve": releve, "suivi": suivi })).into_response()
}

/// `POST /api/admin/opportunites/import` (Authorization: Bearer …) : 204, 400 si le relevé est invalide
async fn importer(State(state): State<AppState>, headers: HeaderMap, Json(releve): Json<Value>) -> StatusCode {
    let o = &state.opportunites;
    let Some(jeton) = o.jeton.as_deref() else { return StatusCode::NOT_FOUND };
    let fourni = headers
        .get(header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "))
        .unwrap_or("");
    if !egal_temps_constant(fourni.as_bytes(), jeton.as_bytes()) {
        return StatusCode::FORBIDDEN;
    }
    if !releve_valide(&releve) {
        return StatusCode::BAD_REQUEST;
    }
    match ecrire(&o.releve, &serde_json::to_vec(&releve).expect("relevé")) {
        Ok(()) => {
            tracing::info!(mails = releve["mails"].as_array().map_or(0, Vec::len), "opportunités importées");
            StatusCode::NO_CONTENT
        }
        Err(e) => {
            tracing::error!("relevé des opportunités : {e}");
            StatusCode::INTERNAL_SERVER_ERROR
        }
    }
}

#[derive(Deserialize)]
struct DemandeSuivi {
    id: String,
    /// null : efface le suivi (retour à « nouveau »)
    statut: Option<String>,
    #[serde(default)]
    note: String,
}

/// `POST /api/admin/opportunites/suivi` : 204, 400 si la demande est invalide
async fn suivre(State(state): State<AppState>, headers: HeaderMap, Json(d): Json<DemandeSuivi>) -> StatusCode {
    if let Err(code) = connecte(&state, &headers) {
        return code;
    }
    let statut_ok = d.statut.as_deref().is_none_or(|s| STATUTS.contains(&s));
    if !id_valide(&d.id) || !statut_ok || d.note.chars().count() > NOTE_MAX {
        return StatusCode::BAD_REQUEST;
    }
    match state.opportunites.poser(&d.id, d.statut.as_deref(), d.note.trim()) {
        Ok(()) => StatusCode::NO_CONTENT,
        Err(e) => {
            tracing::error!("suivi des opportunités : {e}");
            StatusCode::INTERNAL_SERVER_ERROR
        }
    }
}

pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/opportunites", get(lire))
        .route("/opportunites/suivi", post(suivre))
        .route("/opportunites/import", post(importer).layer(DefaultBodyLimit::max(TAILLE_MAX)))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn forme_du_releve() {
        let ok = json!({ "mails": [{ "id": "1a154f1506d3027b", "le": "2026-10-19", "sujet": "x", "expediteur": "a@b.c" }] });
        assert!(releve_valide(&ok));
        assert!(releve_valide(&json!({ "mails": [] })));
        assert!(!releve_valide(&json!({ "mails": [{ "id": "../x", "le": "", "sujet": "", "expediteur": "" }] })));
        assert!(!releve_valide(&json!({ "mails": [{ "id": "1a", "sujet": "x" }] })));
        assert!(!releve_valide(&json!({ "lignes": [] })));
    }

    #[test]
    fn suivi_persiste() {
        let dir = std::env::temp_dir().join(format!("opportunites-{}", std::process::id()));
        let releve = dir.join("opportunites.json");
        let o = Opportunites::new(releve.clone(), None);
        assert!(!o.import_ouvert());
        o.poser("1a2b", Some("a_creuser"), "rappeler lundi").unwrap();
        o.poser("3c4d", Some("ecarte"), "").unwrap();
        o.poser("3c4d", None, "").unwrap();
        let relu = Opportunites::new(releve, Some("j".repeat(32)));
        assert!(relu.import_ouvert());
        let s = relu.suivi.lock().unwrap().clone();
        assert_eq!(s.len(), 1);
        assert_eq!(s["1a2b"].statut, "a_creuser");
        assert_eq!(s["1a2b"].note, "rappeler lundi");
        std::fs::remove_dir_all(&dir).ok();
    }
}
