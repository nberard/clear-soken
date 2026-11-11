//! Lecture des stats Instagram de clearmind-tools dans BigQuery, pour l'espace admin.
//!
//! Lecture seule : compte de service Google avec le seul rôle « lecteur » (portée bigquery.readonly), requêtes
//! écrites ici (jamais de SQL venant du navigateur), et un plafond de coût par requête.

use std::{
    path::Path,
    sync::Mutex,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

/// Plafond de données lues par requête (100 Mo) : les marts font quelques Mo, c'est un garde-fou de coût
const MAX_OCTETS: &str = "100000000";

#[derive(Deserialize)]
struct Cle {
    client_email: String,
    private_key: String,
    #[serde(default = "token_uri_defaut")]
    token_uri: String,
    project_id: Option<String>,
}

fn token_uri_defaut() -> String {
    "https://oauth2.googleapis.com/token".into()
}

#[derive(Serialize)]
struct Revendications<'a> {
    iss: &'a str,
    scope: &'a str,
    aud: &'a str,
    iat: u64,
    exp: u64,
}

pub struct BigQuery {
    cle: Cle,
    pub projet: String,
    pub dataset: String,
    location: String,
    http: reqwest::Client,
    jeton: tokio::sync::Mutex<Option<(String, SystemTime)>>,
}

impl BigQuery {
    /// `cle` : fichier JSON du compte de service ; projet par défaut : celui de la clé
    pub fn depuis_fichier(cle: &Path, projet: Option<String>, dataset: String, location: String) -> Result<Self, String> {
        let raw = std::fs::read_to_string(cle).map_err(|e| format!("lecture de {} impossible : {e}", cle.display()))?;
        let cle: Cle = serde_json::from_str(&raw).map_err(|e| format!("BQ_CLE n'est pas une clé de compte de service : {e}"))?;
        jsonwebtoken::EncodingKey::from_rsa_pem(cle.private_key.as_bytes()).map_err(|e| format!("clé privée illisible : {e}"))?;
        let projet = projet.or_else(|| cle.project_id.clone()).ok_or("BQ_PROJET manquant (et absent de la clé)")?;
        Ok(Self {
            cle,
            projet,
            dataset,
            location,
            http: reqwest::Client::builder().timeout(Duration::from_secs(30)).build().map_err(|e| e.to_string())?,
            jeton: tokio::sync::Mutex::new(None),
        })
    }

    async fn jeton(&self) -> Result<String, String> {
        let mut cache = self.jeton.lock().await;
        if let Some((j, exp)) = cache.as_ref()
            && *exp > SystemTime::now() + Duration::from_secs(60)
        {
            return Ok(j.clone());
        }
        let maintenant = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs();
        let assertion = jsonwebtoken::encode(
            &jsonwebtoken::Header::new(jsonwebtoken::Algorithm::RS256),
            &Revendications {
                iss: &self.cle.client_email,
                scope: "https://www.googleapis.com/auth/bigquery.readonly",
                aud: &self.cle.token_uri,
                iat: maintenant,
                exp: maintenant + 3600,
            },
            &jsonwebtoken::EncodingKey::from_rsa_pem(self.cle.private_key.as_bytes()).map_err(|e| e.to_string())?,
        )
        .map_err(|e| e.to_string())?;
        let rep: Value = self
            .http
            .post(&self.cle.token_uri)
            .form(&[("grant_type", "urn:ietf:params:oauth:grant-type:jwt-bearer"), ("assertion", &assertion)])
            .send()
            .await
            .map_err(|e| format!("Google OAuth injoignable : {e}"))?
            .json()
            .await
            .map_err(|e| e.to_string())?;
        let j = rep["access_token"].as_str().ok_or_else(|| format!("jeton Google refusé : {}", rep["error_description"]))?;
        let duree = rep["expires_in"].as_u64().unwrap_or(3600);
        *cache = Some((j.to_owned(), SystemTime::now() + Duration::from_secs(duree)));
        Ok(j.to_owned())
    }

    /// Exécute une requête et renvoie les lignes en objets JSON (colonnes typées)
    pub async fn requete(&self, sql: &str) -> Result<Vec<Value>, String> {
        let url = format!("https://bigquery.googleapis.com/bigquery/v2/projects/{}/queries", self.projet);
        let rep: Value = self
            .http
            .post(url)
            .bearer_auth(self.jeton().await?)
            .json(&serde_json::json!({
                "query": sql,
                "useLegacySql": false,
                "location": self.location,
                "timeoutMs": 25000,
                "maxResults": 10000,
                "maximumBytesBilled": MAX_OCTETS,
            }))
            .send()
            .await
            .map_err(|e| format!("BigQuery injoignable : {e}"))?
            .json()
            .await
            .map_err(|e| e.to_string())?;
        if let Some(err) = rep.get("error") {
            return Err(format!("BigQuery : {}", err["message"].as_str().unwrap_or("erreur")));
        }
        if rep["jobComplete"] == false {
            return Err("BigQuery : requête trop longue, réessaie dans un instant".into());
        }
        Ok(lignes(&rep))
    }
}

/// Réponse jobs.query (schema.fields + rows[].f[].v, tout en texte) -> objets JSON typés
pub fn lignes(rep: &Value) -> Vec<Value> {
    let champs: Vec<(&str, &str)> = rep["schema"]["fields"]
        .as_array()
        .map(|f| f.iter().map(|c| (c["name"].as_str().unwrap_or(""), c["type"].as_str().unwrap_or(""))).collect())
        .unwrap_or_default();
    rep["rows"]
        .as_array()
        .map(|rows| {
            rows.iter()
                .map(|r| {
                    let mut o = Map::new();
                    for ((nom, typ), cell) in champs.iter().zip(r["f"].as_array().into_iter().flatten()) {
                        o.insert((*nom).into(), valeur(typ, &cell["v"]));
                    }
                    Value::Object(o)
                })
                .collect()
        })
        .unwrap_or_default()
}

fn valeur(typ: &str, v: &Value) -> Value {
    let Some(s) = v.as_str() else { return Value::Null };
    match typ {
        "INTEGER" | "INT64" => s.parse::<i64>().map(Value::from).unwrap_or(Value::Null),
        "FLOAT" | "FLOAT64" | "NUMERIC" | "BIGNUMERIC" => {
            s.parse::<f64>().ok().and_then(serde_json::Number::from_f64).map(Value::Number).unwrap_or(Value::Null)
        }
        "BOOLEAN" | "BOOL" => Value::Bool(s == "true"),
        // TIMESTAMP : secondes depuis 1970 en texte (« 1.7299E9 ») -> date ISO
        "TIMESTAMP" => s
            .parse::<f64>()
            .ok()
            .map(|t| Value::String(iso8601(t as i64)))
            .unwrap_or_else(|| Value::String(s.into())),
        _ => Value::String(s.into()),
    }
}

/// Secondes Unix -> « AAAA-MM-JJTHH:MM:SSZ » (sans dépendance de date)
fn iso8601(t: i64) -> String {
    let (jours, sec) = (t.div_euclid(86400), t.rem_euclid(86400));
    // Algorithme de Howard Hinnant (civil_from_days)
    let z = jours + 719468;
    let era = z.div_euclid(146097);
    let doe = z.rem_euclid(146097);
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = yoe + era * 400 + i64::from(m <= 2);
    format!("{y:04}-{m:02}-{d:02}T{:02}:{:02}:{:02}Z", sec / 3600, sec % 3600 / 60, sec % 60)
}

/// Petit cache mémoire des réponses : les marts ne changent qu'une fois par jour (Airflow)
pub struct Cache {
    duree: Duration,
    entrees: Mutex<std::collections::HashMap<String, (SystemTime, Value)>>,
}

impl Cache {
    pub fn new(duree: Duration) -> Self {
        Self { duree, entrees: Mutex::new(Default::default()) }
    }
    pub fn lire(&self, cle: &str) -> Option<Value> {
        let e = self.entrees.lock().unwrap();
        e.get(cle).filter(|(t, _)| t.elapsed().unwrap_or(Duration::MAX) < self.duree).map(|(_, v)| v.clone())
    }
    pub fn ecrire(&self, cle: &str, v: Value) {
        self.entrees.lock().unwrap().insert(cle.into(), (SystemTime::now(), v));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn conversion_des_lignes() {
        let rep = serde_json::json!({
            "schema": {"fields": [
                {"name": "nom", "type": "STRING"}, {"name": "likes", "type": "INTEGER"},
                {"name": "part", "type": "FLOAT"}, {"name": "attendu", "type": "BOOLEAN"},
                {"name": "vide", "type": "INTEGER"}, {"name": "publie", "type": "TIMESTAMP"}
            ]},
            "rows": [{"f": [{"v": "reel"}, {"v": "42"}, {"v": "0.25"}, {"v": "true"}, {"v": null}, {"v": "1.7299872E9"}]}]
        });
        let l = lignes(&rep);
        assert_eq!(l.len(), 1);
        assert_eq!(l[0]["nom"], "reel");
        assert_eq!(l[0]["likes"], 42);
        assert_eq!(l[0]["part"], 0.25);
        assert_eq!(l[0]["attendu"], true);
        assert!(l[0]["vide"].is_null());
        assert_eq!(l[0]["publie"], "2024-10-27T00:00:00Z");
        assert!(lignes(&serde_json::json!({})).is_empty());
    }

    #[test]
    fn dates() {
        assert_eq!(iso8601(0), "1970-01-01T00:00:00Z");
        assert_eq!(iso8601(1_709_210_096), "2024-02-29T12:34:56Z");
    }
}
