//! Espace admin : index des sessions Claude Code (titres, statuts, mes messages, pièces jointes, PR, artifacts…),
//! pour retrouver dans quelle session j'ai parlé de quoi.
//!
//! Le serveur ne lit pas les sessions lui-même : seule une session Claude y a accès. Elle génère l'index
//! (scripts/sessions-claude-index.py) et l'envoie ici :
//! - `POST /api/admin/claude/import` (Authorization: Bearer CLAUDE_INDEX_JETON) remplace l'index ;
//! - `GET /api/admin/claude` le renvoie aux comptes connectés à l'espace admin.
//!
//! L'index est gardé dans un fichier (CLAUDE_INDEX_FILE, sinon à côté des comptes, volume « comptes ») : il contient
//! des extraits de conversations, il ne doit jamais aller dans git.

use std::path::PathBuf;

use axum::{
    Json, Router,
    extract::{DefaultBodyLimit, State},
    http::{HeaderMap, StatusCode, header},
    response::{IntoResponse, Response},
    routing::{get, post},
};
use serde_json::Value;

use crate::AppState;

/// Taille maximale d'un index envoyé (extraits de messages, pas les fichiers eux-mêmes)
const TAILLE_MAX: usize = 32 * 1024 * 1024;

pub struct IndexClaude {
    fichier: PathBuf,
    /// Sans jeton (ou moins de 32 caractères), l'import est fermé (404)
    jeton: Option<String>,
}

impl IndexClaude {
    pub fn new(fichier: PathBuf, jeton: Option<String>) -> Self {
        Self { fichier, jeton: jeton.filter(|j| j.len() >= 32) }
    }

    pub fn depuis_env() -> Self {
        let env = |k: &str| std::env::var(k).ok().filter(|v| !v.trim().is_empty());
        let fichier = env("CLAUDE_INDEX_FILE").map(PathBuf::from).unwrap_or_else(|| {
            PathBuf::from(env("COMPTES_FILE").unwrap_or_else(|| "comptes/comptes.json".into()))
                .with_file_name("sessions_claude.json")
        });
        Self::new(fichier, env("CLAUDE_INDEX_JETON"))
    }

    pub fn import_ouvert(&self) -> bool {
        self.jeton.is_some()
    }
}

fn egal_temps_constant(a: &[u8], b: &[u8]) -> bool {
    a.len() == b.len() && a.iter().zip(b).fold(0u8, |acc, (x, y)| acc | (x ^ y)) == 0
}

/// Forme minimale attendue : { genere_le, sessions: [ { id, titre, … } ] }
fn index_valide(v: &Value) -> bool {
    v.get("sessions").and_then(Value::as_array).is_some_and(|s| {
        s.iter().all(|x| x.get("id").and_then(Value::as_str).is_some_and(|id| id.starts_with("session_")))
    })
}

/// `GET /api/admin/claude` : l'index tel qu'il a été envoyé, ou { sessions: [] } s'il n'y en a pas encore
async fn lire(State(state): State<AppState>, headers: HeaderMap) -> Response {
    let Some(a) = state.admin.as_ref() else { return StatusCode::NOT_FOUND.into_response() };
    if a.session(&headers).is_none() {
        return StatusCode::UNAUTHORIZED.into_response();
    }
    match tokio::fs::read(&state.claude.fichier).await {
        Ok(octets) => ([(header::CONTENT_TYPE, "application/json")], octets).into_response(),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            Json(serde_json::json!({ "genere_le": null, "sessions": [] })).into_response()
        }
        Err(e) => {
            tracing::error!("index des sessions Claude : {e}");
            StatusCode::INTERNAL_SERVER_ERROR.into_response()
        }
    }
}

/// `POST /api/admin/claude/import` (Authorization: Bearer CLAUDE_INDEX_JETON) : 204, 400 si l'index est invalide
async fn importer(State(state): State<AppState>, headers: HeaderMap, Json(index): Json<Value>) -> StatusCode {
    let Some(jeton) = state.claude.jeton.as_deref() else { return StatusCode::NOT_FOUND };
    let fourni = headers
        .get(header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "))
        .unwrap_or("");
    if !egal_temps_constant(fourni.as_bytes(), jeton.as_bytes()) {
        return StatusCode::FORBIDDEN;
    }
    if !index_valide(&index) {
        return StatusCode::BAD_REQUEST;
    }
    // Écriture atomique : un fichier temporaire puis un renommage, jamais d'index à moitié écrit
    let fichier = &state.claude.fichier;
    let tmp = fichier.with_extension("json.tmp");
    let ecrit = async {
        if let Some(dir) = fichier.parent() {
            tokio::fs::create_dir_all(dir).await?;
        }
        tokio::fs::write(&tmp, serde_json::to_vec(&index)?).await?;
        tokio::fs::rename(&tmp, fichier).await
    };
    match ecrit.await {
        Ok(()) => {
            let n = index["sessions"].as_array().map_or(0, Vec::len);
            tracing::info!(sessions = n, "index des sessions Claude importé");
            StatusCode::NO_CONTENT
        }
        Err(e) => {
            tracing::error!("index des sessions Claude : {e}");
            StatusCode::INTERNAL_SERVER_ERROR
        }
    }
}

pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/claude", get(lire))
        .route("/claude/import", post(importer).layer(DefaultBodyLimit::max(TAILLE_MAX)))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn forme_de_l_index() {
        assert!(index_valide(&serde_json::json!({ "sessions": [] })));
        assert!(index_valide(&serde_json::json!({ "sessions": [{ "id": "session_01abc", "titre": "x" }] })));
        assert!(!index_valide(&serde_json::json!({ "sessions": [{ "id": "autre" }] })));
        assert!(!index_valide(&serde_json::json!({ "lignes": [] })));
    }

    #[test]
    fn jeton_trop_court_ferme_l_import() {
        assert!(!IndexClaude::new("x.json".into(), Some("court".into())).import_ouvert());
        assert!(IndexClaude::new("x.json".into(), Some("a".repeat(32))).import_ouvert());
    }
}
