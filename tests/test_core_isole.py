"""`src/core/` ne connaît aucun framework (CLAUDE.md §4).

C'est la condition qui fait de l'API et du bot deux traductions de la même
règle, et non deux copies qui divergeront.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

RACINE = Path("src/core")
INTERDITS = {"fastapi", "starlette", "aiogram", "uvicorn", "redis", "httpx"}


def _modules_importes(fichier: Path) -> set[str]:
    arbre = ast.parse(fichier.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module and noeud.level == 0:
            modules.add(noeud.module.split(".")[0])
    return modules


@pytest.mark.parametrize("fichier", sorted(RACINE.rglob("*.py")), ids=str)
def test_aucun_framework_importe(fichier: Path) -> None:
    interdits = _modules_importes(fichier) & INTERDITS
    assert not interdits, f"{fichier} importe {sorted(interdits)}"


def test_core_contient_bien_des_modules() -> None:
    """Garde-fou du garde-fou : un dossier vide rendrait le test ci-dessus creux."""
    assert len(list(RACINE.rglob("*.py"))) >= 8


def _resoudre_module_src(nom: str) -> Path | None:
    """Chemin du fichier qui définit `nom` (ex: `src.alerting`), ou `None`
    si `nom` n'est pas un module de `src/` (bibliothèque tierce, ou attribut
    qui n'est pas lui-même un sous-module)."""
    if nom != "src" and not nom.startswith("src."):
        return None
    base = Path(*nom.split("."))
    fichier = base.with_suffix(".py")
    if fichier.is_file():
        return fichier
    paquet = base / "__init__.py"
    if paquet.is_file():
        return paquet
    return None


def _cibles_importees(fichier: Path) -> tuple[set[str], set[Path]]:
    """Renvoie (premier segment de chaque import, fichiers `src/` atteints).

    Pour `from src.core.auth import cles, jetons`, `cles` et `jetons` sont des
    SOUS-MODULES, pas des attributs : `noeud.module` seul ne suffit pas à les
    résoudre, il faut aussi essayer `module.nom_importé`.
    """
    arbre = ast.parse(fichier.read_text(encoding="utf-8"))
    premiers_segments: set[str] = set()
    cibles: set[Path] = set()

    def _essayer(nom: str) -> None:
        chemin = _resoudre_module_src(nom)
        if chemin is not None:
            cibles.add(chemin)

    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            for alias in noeud.names:
                premiers_segments.add(alias.name.split(".")[0])
                _essayer(alias.name)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module and noeud.level == 0:
            premiers_segments.add(noeud.module.split(".")[0])
            _essayer(noeud.module)
            for alias in noeud.names:
                _essayer(f"{noeud.module}.{alias.name}")
    return premiers_segments, cibles


def test_aucun_framework_importe_transitivement() -> None:
    """`test_aucun_framework_importe` ne regarde que le premier segment de
    chaque import : `from src.alerting import ...` donne `src`, jamais dans
    `INTERDITS`. Un module de `core` qui importerait un module applicatif
    (ex: `src.alerting`) qui importe lui-même `fastapi` passerait donc
    inaperçu. Ce test suit les imports `src.*` de façon transitive depuis
    chaque module de `core`, et vérifie qu'aucun module atteint n'importe un
    framework interdit — pas seulement les modules de `core` eux-mêmes."""
    a_visiter = list(RACINE.rglob("*.py"))
    visites: set[Path] = set()
    fautifs: dict[str, set[str]] = {}

    while a_visiter:
        fichier = a_visiter.pop()
        if fichier in visites:
            continue
        visites.add(fichier)
        segments, cibles = _cibles_importees(fichier)
        interdits = segments & INTERDITS
        if interdits:
            fautifs[str(fichier)] = interdits
        a_visiter.extend(c for c in cibles if c not in visites)

    assert not fautifs, f"import interdit atteint transitivement depuis core/ : {fautifs}"
