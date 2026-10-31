//! Comptes des potes : les amis à qui le serveur ouvre des services perso (portail des téléchargements…).
//!
//! Sans aucun lien avec l'appli patients, qui reste sans compte : ni la PWA ni ses pages n'utilisent ces
//! comptes. Le fichier ne contient que le nom, un hash Argon2 du mot de passe et les rôles (« pote »…).
//! Il vit dans le volume Docker `comptes` et se gère en ligne de commande (`make compte`, voir README).
//!
//! Les autres services demandent « ce nom et ce mot de passe sont-ils bons, et quels sont ses rôles ? » via
//! `POST /api/comptes/verifier`, protégé par le jeton COMPTES_JETON et bloqué depuis Internet par Caddy.

use std::{
    io::{BufRead, Write},
    path::{Path, PathBuf},
    sync::{Arc, Mutex},
    time::SystemTime,
};

use argon2::{
    Argon2, PasswordHash, PasswordHasher, PasswordVerifier,
    password_hash::{SaltString, rand_core::OsRng},
};
use axum::{
    Json,
    extract::State,
    http::{HeaderMap, StatusCode, header},
};
use serde::{Deserialize, Serialize};

use crate::AppState;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Compte {
    pub nom: String,
    pub hash: String,
    #[serde(default)]
    pub roles: Vec<String>,
}

/// Même règle que les noms d'utilisateur Linux de transmission-stack : minuscules, chiffres, - et _
pub fn nom_valide(nom: &str) -> bool {
    let mut c = nom.chars();
    matches!(c.next(), Some('a'..='z' | '_'))
        && nom.len() <= 32
        && c.all(|c| matches!(c, 'a'..='z' | '0'..='9' | '_' | '-'))
}

pub fn hacher(mot_de_passe: &str) -> String {
    let sel = SaltString::generate(&mut OsRng);
    Argon2::default()
        .hash_password(mot_de_passe.as_bytes(), &sel)
        .expect("hash Argon2 impossible")
        .to_string()
}

fn hash_correspond(hash: &str, mot_de_passe: &str) -> bool {
    PasswordHash::new(hash)
        .is_ok_and(|h| Argon2::default().verify_password(mot_de_passe.as_bytes(), &h).is_ok())
}

pub fn lire(path: &Path) -> Result<Vec<Compte>, String> {
    match std::fs::read_to_string(path) {
        Ok(raw) => serde_json::from_str(&raw).map_err(|e| format!("{} n'est pas un JSON valide : {e}", path.display())),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(Vec::new()),
        Err(e) => Err(format!("lecture de {} impossible : {e}", path.display())),
    }
}

/// Écriture atomique (fichier temporaire puis renommage) : le serveur ne lit jamais un fichier à moitié écrit
pub fn ecrire(path: &Path, comptes: &[Compte]) -> Result<(), String> {
    let tmp = path.with_extension("json.tmp");
    let json = serde_json::to_string_pretty(comptes).expect("sérialisation des comptes");
    let mut options = std::fs::OpenOptions::new();
    options.write(true).create(true).truncate(true);
    #[cfg(unix)]
    std::os::unix::fs::OpenOptionsExt::mode(&mut options, 0o600);
    options
        .open(&tmp)
        .and_then(|mut f| f.write_all(json.as_bytes()).and_then(|_| f.sync_all()))
        .and_then(|_| std::fs::rename(&tmp, path))
        .map_err(|e| format!("écriture de {} impossible : {e}", path.display()))
}

/// Les comptes en mémoire, relus dès que le fichier change (pas besoin de redémarrer après `make compte`)
pub struct Comptes {
    path: PathBuf,
    cache: Mutex<(Option<SystemTime>, Arc<Vec<Compte>>)>,
}

impl Comptes {
    pub fn new(path: PathBuf) -> Self {
        Self { path, cache: Mutex::new((None, Arc::new(Vec::new()))) }
    }

    fn liste(&self) -> Arc<Vec<Compte>> {
        let mtime = std::fs::metadata(&self.path).and_then(|m| m.modified()).ok();
        let mut cache = self.cache.lock().unwrap();
        if cache.0 != mtime || mtime.is_none() {
            match lire(&self.path) {
                Ok(list) => *cache = (mtime, Arc::new(list)),
                // Fichier abîmé : on garde la dernière version lue plutôt que de couper tout le monde
                Err(e) => tracing::error!("{e}"),
            }
        }
        cache.1.clone()
    }

    /// Le compte si le mot de passe est bon. Un nom inconnu coûte le même temps qu'un mauvais mot de passe.
    pub fn verifier(&self, nom: &str, mot_de_passe: &str) -> Option<Compte> {
        let liste = self.liste();
        match liste.iter().find(|c| c.nom == nom) {
            Some(c) if hash_correspond(&c.hash, mot_de_passe) => Some(c.clone()),
            Some(_) => None,
            None => {
                static FACTICE: std::sync::OnceLock<String> = std::sync::OnceLock::new();
                hash_correspond(FACTICE.get_or_init(|| hacher("factice")), mot_de_passe);
                None
            }
        }
    }
}

#[derive(Deserialize)]
pub struct Demande {
    nom: String,
    mot_de_passe: String,
}

#[derive(Serialize)]
pub struct Reponse {
    nom: String,
    roles: Vec<String>,
}

fn egal_temps_constant(a: &[u8], b: &[u8]) -> bool {
    a.len() == b.len() && a.iter().zip(b).fold(0u8, |acc, (x, y)| acc | (x ^ y)) == 0
}

/// `POST /api/comptes/verifier` (Authorization: Bearer COMPTES_JETON) : 200 { nom, roles } ou 401.
/// Sans COMPTES_JETON configuré, la route n'existe pas (404).
pub async fn verifier(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(demande): Json<Demande>,
) -> Result<Json<Reponse>, StatusCode> {
    let Some(jeton) = state.comptes_jeton.as_deref() else {
        return Err(StatusCode::NOT_FOUND);
    };
    let fourni = headers
        .get(header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "))
        .unwrap_or("");
    if !egal_temps_constant(fourni.as_bytes(), jeton.as_bytes()) {
        return Err(StatusCode::FORBIDDEN);
    }
    let nom = demande.nom.trim().to_lowercase();
    if !nom_valide(&nom) || demande.mot_de_passe.is_empty() || demande.mot_de_passe.len() > 1024 {
        return Err(StatusCode::UNAUTHORIZED);
    }
    let comptes = state.comptes.clone();
    // Argon2 est volontairement lent : hors de la boucle async
    let trouve = tokio::task::spawn_blocking(move || comptes.verifier(&nom, &demande.mot_de_passe))
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    match trouve {
        Some(c) => Ok(Json(Reponse { nom: c.nom, roles: c.roles })),
        None => Err(StatusCode::UNAUTHORIZED),
    }
}

/// `clear-soken-api compte …` : gestion des comptes (lancé par make compte / comptes / compte-supprimer).
/// Le mot de passe arrive sur l'entrée standard, jamais dans la ligne de commande.
pub fn cli(path: &Path, args: &[String]) -> Result<String, String> {
    let mut comptes = lire(path)?;
    let roles = |s: Option<&String>| -> Vec<String> {
        s.map(|s| s.split(',').map(|r| r.trim().to_lowercase()).filter(|r| !r.is_empty()).collect())
            .unwrap_or_else(|| vec!["pote".into()])
    };
    let nom = |i: usize| -> Result<String, String> {
        let n = args.get(i).map(|s| s.trim().to_lowercase()).unwrap_or_default();
        if nom_valide(&n) { Ok(n) } else { Err(format!("nom invalide : « {n} » (minuscules, chiffres, - et _)")) }
    };
    match args.first().map(String::as_str) {
        Some("ajouter") => {
            let nom = nom(1)?;
            let mut mdp = String::new();
            std::io::stdin().lock().read_line(&mut mdp).map_err(|e| e.to_string())?;
            let mdp = mdp.trim_end_matches(['\r', '\n']);
            if mdp.chars().count() < 8 {
                return Err("mot de passe trop court (8 caractères minimum)".into());
            }
            let hash = hacher(mdp);
            let roles = roles(args.get(2));
            let message = match comptes.iter_mut().find(|c| c.nom == nom) {
                Some(c) => {
                    c.hash = hash;
                    c.roles = roles.clone();
                    format!("compte {nom} mis à jour (rôles : {})", roles.join(", "))
                }
                None => {
                    comptes.push(Compte { nom: nom.clone(), hash, roles: roles.clone() });
                    format!("compte {nom} créé (rôles : {})", roles.join(", "))
                }
            };
            ecrire(path, &comptes)?;
            Ok(message)
        }
        Some("roles") => {
            let nom = nom(1)?;
            let roles = roles(args.get(2));
            let c = comptes.iter_mut().find(|c| c.nom == nom).ok_or(format!("pas de compte {nom}"))?;
            c.roles = roles.clone();
            ecrire(path, &comptes)?;
            Ok(format!("rôles de {nom} : {}", roles.join(", ")))
        }
        Some("supprimer") => {
            let nom = nom(1)?;
            let avant = comptes.len();
            comptes.retain(|c| c.nom != nom);
            if comptes.len() == avant {
                return Err(format!("pas de compte {nom}"));
            }
            ecrire(path, &comptes)?;
            Ok(format!("compte {nom} supprimé"))
        }
        Some("liste") => Ok(if comptes.is_empty() {
            "aucun compte (make compte NOM=… pour en créer un)".into()
        } else {
            comptes.iter().map(|c| format!("{:<20} {}", c.nom, c.roles.join(", "))).collect::<Vec<_>>().join("\n")
        }),
        _ => Err("usage : compte ajouter NOM [ROLES] | roles NOM ROLES | supprimer NOM | liste".into()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dossier(nom: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("comptes-{nom}-{}", std::process::id()));
        std::fs::create_dir_all(&d).unwrap();
        d.join("comptes.json")
    }

    #[test]
    fn noms() {
        assert!(nom_valide("psycho"));
        assert!(nom_valide("jean-luc_2"));
        assert!(!nom_valide(""));
        assert!(!nom_valide("Psycho"));
        assert!(!nom_valide("2pac"));
        assert!(!nom_valide("../root"));
        assert!(!nom_valide(&"a".repeat(33)));
    }

    #[test]
    fn verification_et_relecture() {
        let path = dossier("verif");
        let comptes = Comptes::new(path.clone());
        assert!(comptes.verifier("psycho", "motdepasse").is_none());
        ecrire(&path, &[Compte { nom: "psycho".into(), hash: hacher("motdepasse"), roles: vec!["pote".into()] }]).unwrap();
        let c = comptes.verifier("psycho", "motdepasse").expect("compte relu sans redémarrage");
        assert_eq!(c.roles, vec!["pote"]);
        assert!(comptes.verifier("psycho", "mauvais").is_none());
        assert!(comptes.verifier("inconnu", "motdepasse").is_none());
        std::fs::remove_dir_all(path.parent().unwrap()).ok();
    }

    #[test]
    fn cli_roles_et_suppression() {
        let path = dossier("cli");
        ecrire(&path, &[Compte { nom: "psycho".into(), hash: hacher("motdepasse"), roles: vec!["pote".into()] }]).unwrap();
        let a = |v: &[&str]| v.iter().map(|s| s.to_string()).collect::<Vec<_>>();
        assert!(cli(&path, &a(&["roles", "psycho", "pote,admin"])).is_ok());
        assert_eq!(lire(&path).unwrap()[0].roles, vec!["pote", "admin"]);
        assert!(cli(&path, &a(&["liste"])).unwrap().contains("psycho"));
        assert!(cli(&path, &a(&["supprimer", "personne"])).is_err());
        assert!(cli(&path, &a(&["supprimer", "psycho"])).is_ok());
        assert!(lire(&path).unwrap().is_empty());
        std::fs::remove_dir_all(path.parent().unwrap()).ok();
    }
}
