//! Prix des plans, calculés à partir d'un seul prix de référence par jour (dans .env).
//!
//!   PRIX_JOUR_CENTIMES=2       prix Premium par jour, en centimes d'euro (défaut : 2)
//!   ESSAI_JOURS=30             essai gratuit de Premium, en jours (défaut : 30)
//!   REMISE_ANNUELLE_PCT=0      remise sur le paiement annuel, en % (défaut : 0)
//!
//! Mois = jour × 365 / 12, an = jour × 365 − remise, arrondis au centime.

use serde::Serialize;

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Pricing {
    pub devise: &'static str,
    pub prix_jour_centimes: u32,
    pub essai_jours: u32,
    pub remise_annuelle_pct: u32,
    pub plans: Vec<Plan>,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Plan {
    pub id: &'static str,
    pub nom: &'static str,
    /// Prix en centimes ; 0 = gratuit.
    pub jour_centimes: u32,
    pub mois_centimes: u32,
    pub an_centimes: u32,
    pub essai_jours: u32,
    pub sur_invitation: bool,
}

impl Pricing {
    pub fn new(prix_jour_centimes: u32, essai_jours: u32, remise_annuelle_pct: u32) -> Self {
        assert!(
            remise_annuelle_pct <= 100,
            "REMISE_ANNUELLE_PCT doit être entre 0 et 100"
        );
        let day = prix_jour_centimes as u64;
        let month = (day * 365 + 6) / 12; // arrondi au centime le plus proche
        let year = (day * 365 * (100 - remise_annuelle_pct as u64) + 50) / 100;
        let free = |id, nom, sur_invitation| Plan {
            id,
            nom,
            jour_centimes: 0,
            mois_centimes: 0,
            an_centimes: 0,
            essai_jours: 0,
            sur_invitation,
        };
        Self {
            devise: "EUR",
            prix_jour_centimes,
            essai_jours,
            remise_annuelle_pct,
            plans: vec![
                free("free", "Free", false),
                Plan {
                    id: "premium",
                    nom: "Premium",
                    jour_centimes: prix_jour_centimes,
                    mois_centimes: month as u32,
                    an_centimes: year as u32,
                    essai_jours,
                    sur_invitation: false,
                },
                free("dev", "Dev", true),
            ],
        }
    }

    pub fn from_env() -> Self {
        Self::new(
            var("PRIX_JOUR_CENTIMES", 2),
            var("ESSAI_JOURS", 30),
            var("REMISE_ANNUELLE_PCT", 0),
        )
    }
}

fn var(name: &str, default: u32) -> u32 {
    match std::env::var(name) {
        Ok(v) if !v.trim().is_empty() => v
            .trim()
            .parse()
            .unwrap_or_else(|_| panic!("{name} invalide : « {v} » (nombre entier attendu)")),
        _ => default,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn premium(p: &Pricing) -> &Plan {
        p.plans.iter().find(|p| p.id == "premium").unwrap()
    }

    #[test]
    fn derived_from_daily_price() {
        let p = Pricing::new(2, 30, 0);
        let pr = premium(&p);
        assert_eq!(pr.mois_centimes, 61); // 2 × 365 / 12 = 60,8
        assert_eq!(pr.an_centimes, 730);
        assert_eq!(pr.essai_jours, 30);
    }

    #[test]
    fn yearly_discount() {
        let p = Pricing::new(3, 30, 20);
        assert_eq!(premium(&p).an_centimes, 876); // 3 × 365 = 1095, −20 %
        assert_eq!(premium(&p).mois_centimes, 91);
    }

    #[test]
    fn free_and_dev_cost_nothing() {
        let p = Pricing::new(5, 30, 0);
        for id in ["free", "dev"] {
            let plan = p.plans.iter().find(|p| p.id == id).unwrap();
            assert_eq!((plan.mois_centimes, plan.an_centimes), (0, 0));
        }
        assert!(
            p.plans
                .iter()
                .find(|p| p.id == "dev")
                .unwrap()
                .sur_invitation
        );
    }
}
