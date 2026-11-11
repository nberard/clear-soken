//! Espace admin : statistiques Instagram avancées (top des réels, faux comptes, provenance des abonnés).
//!
//! Sans aucun lien avec l'appli patients : réservé aux comptes des potes qui ont le rôle « admin »
//! (`make compte NOM=… ROLES=pote,admin`). Les chiffres viennent des marts dbt de clearmind-tools, lus dans
//! BigQuery (BQ_CLE) ou, pour développer sans Google Cloud, dans des fichiers JSON (ADMIN_DONNEES_DIR).
//!
//! Connexion : `POST /api/admin/connexion` pose un cookie de session HttpOnly, Secure, SameSite=Strict, limité à
//! /api/admin et valable 12 h. Les sessions ne vivent qu'en mémoire : un redémarrage déconnecte tout le monde.

use std::{
    collections::HashMap,
    path::PathBuf,
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};

use argon2::password_hash::rand_core::{OsRng, RngCore};
use axum::{
    Json, Router,
    extract::{Path, State},
    http::{HeaderMap, HeaderValue, StatusCode, header},
    response::{IntoResponse, Response},
    routing::{get, post},
};
use serde::Deserialize;
use serde_json::{Value, json};
use tower_http::set_header::SetResponseHeaderLayer;

use crate::{
    AppState,
    bigquery::{BigQuery, Cache},
    comptes::nom_valide,
};

const COOKIE: &str = "cs_admin";
const DUREE_SESSION: Duration = Duration::from_secs(12 * 3600);
/// Au-delà de 10 mots de passe faux en 10 minutes (tous noms confondus), la connexion est suspendue
const ECHECS_MAX: u32 = 10;
const FENETRE_ECHECS: Duration = Duration::from_secs(600);

/// Les vues proposées : (nom, mart dbt, requête). Le navigateur choisit une vue, jamais le SQL
const VUES: &[(&str, &str, &str)] = &[
    ("publications", "mart_instagram_publications", "select * from `{t}` order by published_at desc"),
    ("comptes", "mart_instagram_comptes", "select * from `{t}` order by pct_faux desc, reels_likes desc limit 5000"),
    ("qualite", "mart_instagram_qualite", "select * from `{t}`"),
    ("pays", "mart_audience_pays", "select * from `{t}` where platform = 'instagram' order by abonnes desc"),
];

pub enum Source {
    BigQuery(Box<BigQuery>),
    /// `<dossier>/<mart>.json` (ex. mart_instagram_comptes.json) : un tableau d'objets, colonnes du mart
    Fichiers(PathBuf),
}

pub struct Admin {
    source: Source,
    cache: Cache,
    sessions: Mutex<HashMap<String, (String, Instant)>>,
    echecs: Mutex<(Instant, u32)>,
}

impl Admin {
    pub fn new(source: Source) -> Self {
        Self {
            source,
            cache: Cache::new(Duration::from_secs(600)),
            sessions: Mutex::new(HashMap::new()),
            echecs: Mutex::new((Instant::now(), 0)),
        }
    }

    pub fn description(&self) -> String {
        match &self.source {
            Source::BigQuery(bq) => format!("BigQuery {}.{}", bq.projet, bq.dataset),
            Source::Fichiers(d) => format!("fichiers {}", d.display()),
        }
    }

    fn ouvrir_session(&self, nom: &str) -> String {
        let mut octets = [0u8; 32];
        OsRng.fill_bytes(&mut octets);
        let jeton: String = octets.iter().map(|b| format!("{b:02x}")).collect();
        let mut s = self.sessions.lock().unwrap();
        s.retain(|_, (_, fin)| *fin > Instant::now());
        s.insert(jeton.clone(), (nom.to_owned(), Instant::now() + DUREE_SESSION));
        jeton
    }

    fn session(&self, headers: &HeaderMap) -> Option<String> {
        let jeton = jeton_cookie(headers)?;
        let s = self.sessions.lock().unwrap();
        s.get(jeton).filter(|(_, fin)| *fin > Instant::now()).map(|(nom, _)| nom.clone())
    }

    fn trop_d_echecs(&self) -> bool {
        let e = self.echecs.lock().unwrap();
        e.1 >= ECHECS_MAX && e.0.elapsed() < FENETRE_ECHECS
    }

    fn noter_echec(&self) {
        let mut e = self.echecs.lock().unwrap();
        if e.0.elapsed() >= FENETRE_ECHECS {
            *e = (Instant::now(), 0);
        }
        e.1 += 1;
    }

    async fn vue(&self, vue: &str) -> Result<Value, String> {
        if let Some(v) = self.cache.lire(vue) {
            return Ok(v);
        }
        let (_, mart, sql) = VUES.iter().find(|(n, _, _)| *n == vue).ok_or("vue inconnue")?;
        let lignes = match &self.source {
            Source::BigQuery(bq) => {
                let table = format!("{}.{}.{mart}", bq.projet, bq.dataset);
                Value::from(bq.requete(&sql.replace("{t}", &table)).await?)
            }
            Source::Fichiers(dir) => {
                let path = dir.join(format!("{mart}.json"));
                let raw = tokio::fs::read_to_string(&path).await.map_err(|e| format!("{} : {e}", path.display()))?;
                serde_json::from_str(&raw).map_err(|e| format!("{} : {e}", path.display()))?
            }
        };
        let v = json!({ "lignes": lignes, "lu_le": horodatage() });
        self.cache.ecrire(vue, v.clone());
        Ok(v)
    }
}

fn horodatage() -> u64 {
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0)
}

fn jeton_cookie(headers: &HeaderMap) -> Option<&str> {
    headers
        .get_all(header::COOKIE)
        .iter()
        .filter_map(|v| v.to_str().ok())
        .flat_map(|v| v.split(';'))
        .find_map(|c| c.trim().strip_prefix(COOKIE).and_then(|r| r.strip_prefix('=')))
}

fn admin(state: &AppState) -> Result<&Arc<Admin>, StatusCode> {
    state.admin.as_ref().ok_or(StatusCode::NOT_FOUND)
}

#[derive(Deserialize)]
pub struct Connexion {
    nom: String,
    mot_de_passe: String,
}

/// `POST /api/admin/connexion` { nom, mot_de_passe } : 200 + cookie si le compte a le rôle admin,
/// 401 sinon (même réponse pour un nom inconnu, un mauvais mot de passe ou un compte sans le rôle).
async fn connexion(State(state): State<AppState>, Json(c): Json<Connexion>) -> Result<Response, StatusCode> {
    let admin = admin(&state)?.clone();
    if admin.trop_d_echecs() {
        return Err(StatusCode::TOO_MANY_REQUESTS);
    }
    let nom = c.nom.trim().to_lowercase();
    if !nom_valide(&nom) || c.mot_de_passe.is_empty() || c.mot_de_passe.len() > 1024 {
        admin.noter_echec();
        return Err(StatusCode::UNAUTHORIZED);
    }
    let comptes = state.comptes.clone();
    let trouve = tokio::task::spawn_blocking(move || comptes.verifier(&nom, &c.mot_de_passe))
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    let Some(compte) = trouve.filter(|c| c.roles.iter().any(|r| r == "admin")) else {
        admin.noter_echec();
        return Err(StatusCode::UNAUTHORIZED);
    };
    let jeton = admin.ouvrir_session(&compte.nom);
    tracing::info!(nom = %compte.nom, "connexion à l'espace admin");
    let cookie = format!(
        "{COOKIE}={jeton}; Path=/api/admin; HttpOnly; Secure; SameSite=Strict; Max-Age={}",
        DUREE_SESSION.as_secs()
    );
    Ok(([(header::SET_COOKIE, cookie)], Json(json!({ "nom": compte.nom }))).into_response())
}

async fn deconnexion(State(state): State<AppState>, headers: HeaderMap) -> Result<Response, StatusCode> {
    let admin = admin(&state)?;
    if let Some(j) = jeton_cookie(&headers) {
        admin.sessions.lock().unwrap().remove(j);
    }
    let efface = format!("{COOKIE}=; Path=/api/admin; HttpOnly; Secure; SameSite=Strict; Max-Age=0");
    Ok(([(header::SET_COOKIE, efface)], StatusCode::NO_CONTENT).into_response())
}

/// `GET /api/admin/moi` : { nom } si la session est ouverte, 401 sinon
async fn moi(State(state): State<AppState>, headers: HeaderMap) -> Result<Json<Value>, StatusCode> {
    let nom = admin(&state)?.session(&headers).ok_or(StatusCode::UNAUTHORIZED)?;
    Ok(Json(json!({ "nom": nom })))
}

/// `GET /api/admin/stats/{vue}` (publications, comptes, qualite, pays) : { lignes, lu_le }
async fn stats(State(state): State<AppState>, headers: HeaderMap, Path(vue): Path<String>) -> Response {
    let admin = match admin(&state) {
        Ok(a) => a,
        Err(s) => return s.into_response(),
    };
    if admin.session(&headers).is_none() {
        return StatusCode::UNAUTHORIZED.into_response();
    }
    if !VUES.iter().any(|(n, _, _)| *n == vue) {
        return StatusCode::NOT_FOUND.into_response();
    }
    match admin.vue(&vue).await {
        Ok(v) => Json(v).into_response(),
        Err(e) => {
            tracing::error!(vue, "stats admin : {e}");
            (StatusCode::BAD_GATEWAY, Json(json!({ "erreur": e }))).into_response()
        }
    }
}

pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/connexion", post(connexion))
        .route("/deconnexion", post(deconnexion))
        .route("/moi", get(moi))
        .route("/stats/{vue}", get(stats))
        // Rien de l'admin ne doit rester dans un cache (navigateur, service worker, proxy)
        .layer(SetResponseHeaderLayer::overriding(header::CACHE_CONTROL, HeaderValue::from_static("no-store")))
}

/// Source des stats d'après l'environnement : BQ_CLE (+ BQ_PROJET, BQ_DATASET, BQ_LOCATION) ou ADMIN_DONNEES_DIR.
/// Ni l'un ni l'autre : pas d'espace admin (404).
pub fn depuis_env() -> Option<Admin> {
    let env = |k: &str| std::env::var(k).ok().filter(|v| !v.trim().is_empty());
    if let Some(cle) = env("BQ_CLE") {
        let dataset = env("BQ_DATASET").unwrap_or_else(|| "clearmind_or".into());
        let location = env("BQ_LOCATION").unwrap_or_else(|| "EU".into());
        match BigQuery::depuis_fichier(cle.as_ref(), env("BQ_PROJET"), dataset, location) {
            Ok(bq) => return Some(Admin::new(Source::BigQuery(Box::new(bq)))),
            Err(e) => {
                tracing::error!("espace admin désactivé : {e}");
                return None;
            }
        }
    }
    env("ADMIN_DONNEES_DIR").map(|d| Admin::new(Source::Fichiers(d.into())))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lecture_du_cookie() {
        let mut h = HeaderMap::new();
        h.insert(header::COOKIE, HeaderValue::from_static("autre=1; cs_admin=abc123; x=2"));
        assert_eq!(jeton_cookie(&h), Some("abc123"));
        let mut h = HeaderMap::new();
        h.insert(header::COOKIE, HeaderValue::from_static("cs_admin_faux=zzz"));
        assert_eq!(jeton_cookie(&h), None);
    }

    #[test]
    fn requetes_sans_injection() {
        // Chaque vue lit un mart précis, avec une requête fixe
        for (_, mart, q) in VUES {
            assert!(mart.starts_with("mart_") && q.contains("`{t}`"));
        }
    }
}
