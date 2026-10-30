"""Import de l'historique Google Fit (Takeout) : lecture des CSV, sans base de données."""
import io
import zipfile
from datetime import date

from healthsync import takeout

ENTETE_JOUR = ("Heure de début,Heure de fin,Nombre de minutes actives,Calories (kcal),Distance (m),Points cardio,"
               "Fréquence cardiaque moyenne (bpm),Fréquence cardiaque maximale (bpm),Fréquence cardiaque minimale (bpm),"
               "Nombre de pas,Poids moyen (kg)\n")
JOUR = ENTETE_JOUR + (
    "00:00:00.000+01:00,00:15:00.000+01:00,,20.5,,,,,,,\n"
    "08:00:00.000+01:00,08:15:00.000+01:00,10,35.5,800.2,,90,120,70,1200,72.4\n"
    "08:15:00.000+01:00,08:30:00.000+01:00,5,30,400,,100,130,80,600,\n"
)
RESUME = ("Date,Nombre de minutes actives,Calories (kcal),Distance (m),Nombre de pas\n"
          "2024-03-12,40,2100.5,5000,7000\n"
          "2024-03-13,,,,\n")


def _zip(fichiers: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nom, texte in fichiers.items():
            z.writestr(nom, texte)
    return buf.getvalue()


def test_un_jour_additionne_les_tranches():
    m = takeout.lire_jour(JOUR)
    assert m["steps.countSum"] == 1800
    assert m["distance.millimetersSum"] == 1200.2 * 1000
    assert m["total-calories.kcalSum"] == 86
    assert m["heart-rate.beatsPerMinuteAvg"] == 95
    assert m["heart-rate.beatsPerMinuteMax"] == 130
    assert m["heart-rate.beatsPerMinuteMin"] == 70
    assert m["weight.kilograms"] == 72.4


def test_resume_ignore_les_jours_vides():
    r = takeout.lire_resume(RESUME)
    assert list(r) == [date(2024, 3, 12)]
    assert r[date(2024, 3, 12)]["steps.countSum"] == 7000


def test_zip_takeout_le_resume_fait_foi(tmp_path):
    dossier = "Takeout/Fit/Métriques d'activité quotidiennes/"
    (tmp_path / "partie01.zip").write_bytes(_zip({
        dossier + "2024-03-12.csv": JOUR,
        dossier + "2024-03-11.csv": JOUR,
        dossier + "Métriques d'activité quotidiennes.csv": RESUME,
        "Takeout/Drive/autre.csv": RESUME,  # hors de Fit : ignoré
    }))
    par_jour = takeout.collecter([tmp_path])
    assert sorted(par_jour) == [date(2024, 3, 11), date(2024, 3, 12)]
    assert par_jour[date(2024, 3, 12)]["steps.countSum"] == 7000  # le résumé
    assert par_jour[date(2024, 3, 12)]["heart-rate.beatsPerMinuteMax"] == 130  # complété par le fichier du jour
    assert par_jour[date(2024, 3, 11)]["steps.countSum"] == 1800


def test_export_en_anglais(tmp_path):
    (tmp_path / "t.zip").write_bytes(_zip({
        "Takeout/Fit/Daily activity metrics/Daily activity metrics.csv":
            "Date,Move Minutes count,Calories (kcal),Distance (m),Average heart rate (bpm),Step count\n"
            "2023-01-02,12,1900,3000,65,4321\n"}))
    m = takeout.collecter([tmp_path])[date(2023, 1, 2)]
    assert m["steps.countSum"] == 4321 and m["heart-rate.beatsPerMinuteAvg"] == 65
