"""Configuration : variables d'environnement + casquettes.toml."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ICI = Path(__file__).resolve().parent.parent


@dataclass
class Casquette:
    nom: str
    description: str
    prive: bool = False
    mots_cles: list[str] = field(default_factory=list)


@dataclass
class Config:
    db_path: str
    casquettes: dict[str, Casquette]
    # Backend « API » (pro, perso, santé physique) : mistral ou anthropic
    api: str = "mistral"
    mistral_key: str = ""
    mistral_model: str = "mistral-small-latest"
    anthropic_key: str = ""
    anthropic_model: str = "claude-haiku-5-5"
    # Backend « local » (casquettes privées) : Ollama sur ton PC
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    @property
    def privees(self) -> set[str]:
        return {n for n, c in self.casquettes.items() if c.prive}


def charger_casquettes(path: str | Path) -> dict[str, Casquette]:
    with open(path, "rb") as f:
        brut = tomllib.load(f)
    return {
        nom: Casquette(
            nom=nom,
            description=v.get("description", nom),
            prive=bool(v.get("prive", False)),
            mots_cles=[m.lower() for m in v.get("mots_cles", [])],
        )
        for nom, v in brut.items()
    }


def charger() -> Config:
    e = os.environ.get
    return Config(
        db_path=e("MEMOIRE_DB", str(ICI / "data" / "memoire.db")),
        casquettes=charger_casquettes(e("MEMOIRE_CASQUETTES", str(ICI / "casquettes.toml"))),
        api=e("MEMOIRE_API", "mistral"),
        mistral_key=e("MISTRAL_API_KEY", ""),
        mistral_model=e("MISTRAL_MODEL", "mistral-small-latest"),
        anthropic_key=e("ANTHROPIC_API_KEY", ""),
        anthropic_model=e("ANTHROPIC_MODEL", "claude-haiku-5-5"),
        ollama_url=e("OLLAMA_URL", "http://localhost:11434"),
        ollama_model=e("OLLAMA_MODEL", "qwen2.5:7b"),
    )
