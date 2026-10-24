//! Clear Soken — API et serveur de la PWA.
//!
//! Choix de conception : aucune donnée de santé ne transite par ce serveur.
//! Les notes du patient restent sur son téléphone ; l'API ne sert que des
//! contenus publics (annuaire de ressources).

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
            HeaderValue::from_static("camera=(), microphone=(), geolocation=()"),
        ))
}

fn load_resources(path: &PathBuf) -> Vec<Resource> {
    let raw = std::fs::read_to_string(path)
        .unwrap_or_else(|e| panic!("lecture de {} impossible : {e}", path.display()));
    serde_json::from_str(&raw)
        .unwrap_or_else(|e| panic!("{} n'est pas un JSON valide : {e}", path.display()))
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::try_from_default_env().unwrap_or_else(|_| "info".into()))
        .init();

    let config = Config::from_env();
    let resources = load_resources(&config.resources_file);
    tracing::info!(count = resources.len(), "ressources chargées");

    let state = AppState { resources: Arc::new(resources) };
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
        app(AppState { resources: Arc::new(resources) }, "../frontend/build".into())
    }

    #[tokio::test]
    async fn health_ok() {
        let res = test_app()
            .oneshot(Request::get("/api/health").body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(res.status(), 200);
        assert_eq!(res.headers()["referrer-policy"], "no-referrer");
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

    #[test]
    fn resource_ids_are_unique() {
        let list = load_resources(&"data/resources.json".into());
        let mut ids: Vec<_> = list.iter().map(|r| &r.id).collect();
        ids.sort();
        ids.dedup();
        assert_eq!(ids.len(), list.len());
    }
}
