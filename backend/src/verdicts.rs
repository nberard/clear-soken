//! Verdicts posés à la main dans l'espace admin sur les comptes Instagram analysés : « vrai », « faux », ou
//! « retiré » (je ne le suis plus). Un verdict l'emporte sur le pourcentage calculé : le compte quitte la liste du
//! ménage. Gardés dans un petit fichier JSON à côté des comptes (volume Docker « comptes »), jamais dans BigQuery.
//! Plus tard, ces verdicts pourront servir d'exemples pour recaler les poids du score (clearmind-tools).

use std::{
    collections::BTreeMap,
    io::Write,
    path::{Path, PathBuf},
    sync::Mutex,
};

use serde::{Deserialize, Serialize};

pub const VALEURS: &[&str] = &["vrai", "faux", "retire"];

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Verdict {
    pub verdict: String,
    pub nom_compte: String,
    /// Date du verdict (AAAA-MM-JJ)
    pub le: String,
}

pub struct Verdicts {
    path: Option<PathBuf>,
    data: Mutex<BTreeMap<String, Verdict>>,
}

impl Verdicts {
    /// path None : en mémoire seulement (tests, dev)
    pub fn new(path: Option<PathBuf>) -> Self {
        let data = path
            .as_deref()
            .and_then(|p| std::fs::read_to_string(p).ok())
            .and_then(|raw| serde_json::from_str(&raw).ok())
            .unwrap_or_default();
        Self { path, data: Mutex::new(data) }
    }

    pub fn tous(&self) -> BTreeMap<String, Verdict> {
        self.data.lock().unwrap().clone()
    }

    /// verdict None : efface le verdict (retour au pourcentage calculé)
    pub fn poser(&self, compte_id: &str, nom_compte: &str, verdict: Option<&str>, le: &str) -> Result<(), String> {
        let mut data = self.data.lock().unwrap();
        match verdict {
            Some(v) => {
                data.insert(
                    compte_id.to_owned(),
                    Verdict { verdict: v.to_owned(), nom_compte: nom_compte.to_owned(), le: le.to_owned() },
                );
            }
            None => {
                data.remove(compte_id);
            }
        }
        match &self.path {
            Some(p) => ecrire(p, &data),
            None => Ok(()),
        }
    }
}

/// Écriture atomique (fichier temporaire puis renommage), lisible par l'appli seulement
fn ecrire(path: &Path, data: &BTreeMap<String, Verdict>) -> Result<(), String> {
    let tmp = path.with_extension("json.tmp");
    let json = serde_json::to_string_pretty(data).expect("sérialisation des verdicts");
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

/// Identifiant Instagram (chiffres) et nom de compte Instagram (lettres, chiffres, . et _)
pub fn demande_valide(compte_id: &str, nom_compte: &str, verdict: Option<&str>) -> bool {
    !compte_id.is_empty()
        && compte_id.len() <= 32
        && compte_id.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
        && nom_compte.len() <= 64
        && nom_compte.chars().all(|c| c.is_ascii_alphanumeric() || c == '.' || c == '_')
        && verdict.is_none_or(|v| VALEURS.contains(&v))
}

/// Date du jour (UTC) sans dépendance de date
pub fn aujourdhui() -> String {
    let jours = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0)
        as i64
        / 86400;
    let z = jours + 719468;
    let era = z.div_euclid(146097);
    let doe = z.rem_euclid(146097);
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = yoe + era * 400 + i64::from(m <= 2);
    format!("{y:04}-{m:02}-{d:02}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn validation() {
        assert!(demande_valide("17841400000", "piwi78000", Some("vrai")));
        assert!(demande_valide("17841400000", "jean.marc_2", None));
        assert!(!demande_valide("", "x", Some("vrai")));
        assert!(!demande_valide("1", "x", Some("peut-etre")));
        assert!(!demande_valide("1", "../etc", Some("faux")));
        assert!(!demande_valide("1/2", "x", Some("faux")));
    }

    #[test]
    fn persistance() {
        let dir = std::env::temp_dir().join(format!("verdicts-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("verdicts_instagram.json");
        let v = Verdicts::new(Some(path.clone()));
        v.poser("1", "piwi78000", Some("vrai"), "2026-11-17").unwrap();
        v.poser("2", "bot123", Some("retire"), "2026-11-17").unwrap();
        v.poser("2", "bot123", None, "2026-11-17").unwrap();
        let relu = Verdicts::new(Some(path)).tous();
        assert_eq!(relu.len(), 1);
        assert_eq!(relu["1"].verdict, "vrai");
        std::fs::remove_dir_all(&dir).ok();
        assert_eq!(aujourdhui().len(), 10);
    }
}
