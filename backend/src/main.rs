//! Clear Soken — API et serveur de la PWA.
//!
//! Choix de conception : aucune donnée de santé ne transite par ce serveur.
//! Les notes du patient restent sur son téléphone ; l'API ne sert que des
//! contenus publics (annuaire de ressources, centres d'addictologie).
//! Le tri des centres par distance se fait sur le téléphone : la position
//! du patient n'est jamais envoyée ici.

mod pricing;

use std::{env, net::SocketAddr, path::PathBuf, sync::Arc};

use axum::{
    Json, Router,
    extract::State,
    http::{HeaderName, HeaderValue, header},
    routing::get,
};
use serde::{Deserialize, Serialize};
use tower_http::{
    compression::CompressionLayer,
    services::{ServeDir, ServeFile},
    set_header::SetResponseHeaderLayer,
};
use tracing_subscriber::EnvFilter;

pub use pricing::Pricing;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Resource {
    pub id: String,
    pub name: String,
    pub kind: String,
    pub description: String,
    pub city: Option<String>,
    pub phone: Option<String>,
    pub url: Option<String>,
}

#[derive(Clone)]
pub struct AppState {
    pub resources: Arc<Vec<Resource>>,
    pub centres: Arc<Vec<serde_json::Value>>,
    pub pricing: Arc<Pricing>,
}

pub struct Config {
    pub bind: SocketAddr,
    pub static_dir: PathBuf,
    pub resources_file: PathBuf,
}

impl Config {
    fn from_env() -> Self {
        Self {
            bind: env::var("BIND")
                .unwrap_or_else(|_| "0.0.0.0:8080".into())
                .parse()
                .expect("BIND invalide (ex. 0.0.0.0:8080)"),
            static_dir: env::var("STATIC_DIR")
                .unwrap_or_else(|_| "../frontend/build".into())
                .into(),
            resources_file: env::var("RESOURCES_FILE")
                .unwrap_or_else(|_| "data/resources.json".into())
                .into(),
        }
    }
}

async fn health() -> &'static str {
    "ok"
}

/// Prix des plans Free / Premium / Dev, calculés depuis PRIX_JOUR_CENTIMES (.env).
async fn plans(State(state): State<AppState>) -> Json<Pricing> {
    Json(state.pricing.as_ref().clone())
}

/// Centres d'addictologie : annuaire FINESS généré par `make centres` + lieux conseillés par l'équipe.
async fn list_centres(State(state): State<AppState>) -> Json<Vec<serde_json::Value>> {
    Json(state.centres.as_ref().clone())
}

async fn list_resources(State(state): State<AppState>) -> Json<Vec<Resource>> {
    Json(state.resources.as_ref().clone())
}

pub fn app(state: AppState, static_dir: PathBuf) -> Router {
    let spa = ServeDir::new(&static_dir)
        .precompressed_br()
        .precompressed_gzip()
        .fallback(ServeFile::new(static_dir.join("200.html")));

    let api = Router::new()
        .route("/health", get(health))
        .route("/resources", get(list_resources))
        .route("/centres", get(list_centres))
        .route("/plans", get(plans))
        .with_state(state)
        .layer(CompressionLayer::new());

    Router::new()
        .nest("/api", api)
        .fallback_service(spa)
        // En-têtes de sécurité : pas de referrer, pas d'iframe, pas de tiers.
        .layer(SetResponseHeaderLayer::overriding(
            header::REFERRER_POLICY,
            HeaderValue::from_static("no-referrer"),
        ))
        .layer(SetResponseHeaderLayer::overriding(
            header::X_CONTENT_TYPE_OPTIONS,
            HeaderValue::from_static("nosniff"),
        ))
        .layer(SetResponseHeaderLayer::overriding(
            header::X_FRAME_OPTIONS,
            HeaderValue::from_static("DENY"),
        ))
        .layer(SetResponseHeaderLayer::overriding(
            HeaderName::from_static("permissions-policy"),
            // La géolocalisation sert à « Trouver un centre » ; elle reste sur le téléphone.
            HeaderValue::from_static("camera=(), microphone=(), geolocation=(self)"),
        ))
}

/// Charge les centres : `centres.json` (généré par scripts/centres-finess.py, absent tant que
/// `make centres` n'a pas tourné) puis `centres-equipe.json` (tenu à la main, marqué « conseillé »).
/// Une entrée sans coordonnées valides est ignorée.
pub fn load_centres(dir: &std::path::Path) -> Vec<serde_json::Value> {
    let mut out = Vec::new();
    for (file, equipe) in [("centres.json", false), ("centres-equipe.json", true)] {
        let path = dir.join(file);
        let Ok(raw) = std::fs::read_to_string(&path) else {
            tracing::warn!("{} absent : lancer make centres", path.display());
            continue;
        };
        let list: Vec<serde_json::Value> = serde_json::from_str(&raw)
            .unwrap_or_else(|e| panic!("{} n'est pas un JSON valide : {e}", path.display()));
        for mut c in list {
            let ok = ["lat", "lon"].iter().all(|k| c[k].as_f64().is_some_and(f64::is_finite))
                && c["id"].is_string()
                && c["nom"].is_string();
            if !ok {
                tracing::warn!(entree = %c, "centre ignoré (id, nom, lat ou lon manquant)");
                continue;
            }
            if equipe {
                c["equipe"] = true.into();
            }
            out.push(c);
        }
    }
    out
}

fn load_resources(path: &PathBuf) -> Vec<Resource> {
    let raw = std::fs::read_to_string(path)
        .unwrap_or_else(|e| panic!("lecture de {} impossible : {e}", path.display()));
    serde_json::from_str(&raw)
        .unwrap_or_else(|e| panic!("{} n'est pas un JSON valide : {e}", path.display()))
}

/// `clear-soken-api --healthcheck` : utilisé par le HEALTHCHECK Docker
/// (l'image n'embarque pas curl). Code retour 0 si /api/health répond.
fn healthcheck() -> ! {
    use std::io::{Read, Write};
    let port = env::var("BIND")
        .ok()
        .and_then(|b| b.rsplit(':').next().map(str::to_owned))
        .unwrap_or_else(|| "8080".into());
    let ok = std::net::TcpStream::connect(format!("127.0.0.1:{port}"))
        .and_then(|mut s| {
            s.set_read_timeout(Some(std::time::Duration::from_secs(2)))?;
            s.write_all(b"GET /api/health HTTP/1.0\r\nHost: localhost\r\n\r\n")?;
            let mut buf = String::new();
            s.read_to_string(&mut buf)?;
            Ok(buf.starts_with("HTTP/1.0 200") || buf.starts_with("HTTP/1.1 200"))
        })
        .unwrap_or(false);
    std::process::exit(if ok { 0 } else { 1 });
}

#[tokio::main]
async fn main() {
    if env::args().any(|a| a == "--healthcheck") {
        healthcheck();
    }

    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::try_from_default_env().unwrap_or_else(|_| "info".into()))
        .init();

    let config = Config::from_env();
    let resources = load_resources(&config.resources_file);
    tracing::info!(count = resources.len(), "ressources chargées");
    let centres = load_centres(config.resources_file.parent().unwrap_or(std::path::Path::new(".")));
    tracing::info!(count = centres.len(), "centres d'addictologie chargés");

    let pricing = Pricing::from_env();
    tracing::info!(
        jour = pricing.prix_jour_centimes,
        essai = pricing.essai_jours,
        "prix Premium (centimes/jour) chargé"
    );

    let state = AppState {
        resources: Arc::new(resources),
        centres: Arc::new(centres),
        pricing: Arc::new(pricing),
    };
    let router = app(state, config.static_dir);

    let listener = tokio::net::TcpListener::bind(config.bind).await.expect("bind impossible");
    tracing::info!("Clear Soken écoute sur http://{}", config.bind);
    axum::serve(listener, router)
        .with_graceful_shutdown(async {
            let _ = tokio::signal::ctrl_c().await;
        })
        .await
        .expect("erreur serveur");
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{body::Body, http::Request};
    use http_body_util::BodyExt;
    use tower::ServiceExt;

    fn test_app() -> Router {
        let resources = load_resources(&"data/resources.json".into());
        let pricing = Arc::new(Pricing::new(2, 30, 0));
        app(
            AppState {
                resources: Arc::new(resources),
                centres: Arc::new(vec![serde_json::json!({"id": "t", "nom": "Test", "lat": 45.0, "lon": 5.0})]),
                pricing,
            },
            "../frontend/build".into(),
        )
    }

    #[tokio::test]
    async fn health_ok() {
        let res = test_app()
            .oneshot(Request::get("/api/health").body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(res.status(), 200);
        assert_eq!(res.headers()["referrer-policy"], "no-referrer");
        assert!(res.headers()["permissions-policy"].to_str().unwrap().contains("geolocation=(self)"));
    }

    #[tokio::test]
    async fn resources_are_served() {
        let res = test_app()
            .oneshot(Request::get("/api/resources").body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(res.status(), 200);
        let body = res.into_body().collect().await.unwrap().to_bytes();
        let list: Vec<Resource> = serde_json::from_slice(&body).unwrap();
        assert!(list.iter().any(|r| r.id == "3114"));
    }

    #[tokio::test]
    async fn plans_are_served() {
        let res = test_app()
            .oneshot(Request::get("/api/plans").body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(res.status(), 200);
        let body = res.into_body().collect().await.unwrap().to_bytes();
        let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["prix_jour_centimes"], 2);
        assert_eq!(json["plans"][1]["mois_centimes"], 61);
    }

    #[tokio::test]
    async fn centres_are_served() {
        let res = test_app()
            .oneshot(Request::get("/api/centres").body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(res.status(), 200);
        let body = res.into_body().collect().await.unwrap().to_bytes();
        let list: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
        assert_eq!(list[0]["id"], "t");
    }

    #[test]
    fn centres_equipe_are_flagged_and_invalid_skipped() {
        let dir = std::env::temp_dir().join(format!("centres-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("centres.json"), r#"[{"id":"a","nom":"A","lat":45.1,"lon":5.7},{"id":"b","nom":"B"}]"#).unwrap();
        std::fs::write(dir.join("centres-equipe.json"), r#"[{"id":"e","nom":"E","lat":45.2,"lon":5.8}]"#).unwrap();
        let list = load_centres(&dir);
        std::fs::remove_dir_all(&dir).ok();
        assert_eq!(list.len(), 2);
        assert!(list[0].get("equipe").is_none());
        assert_eq!(list[1]["equipe"], true);
    }

    #[test]
    fn centres_equipe_file_is_valid() {
        // Le fichier tenu à la main doit rester un JSON valide (sinon l'API refuse de démarrer).
        let raw = std::fs::read_to_string("data/centres-equipe.json").unwrap();
        let _: Vec<serde_json::Value> = serde_json::from_str(&raw).unwrap();
    }

    #[test]
    fn resource_ids_are_unique() {
        let list = load_resources(&"data/resources.json".into());
        let mut ids: Vec<_> = list.iter().map(|r| &r.id).collect();
        ids.sort();
        ids.dedup();
        assert_eq!(ids.len(), list.len());
    }
}
