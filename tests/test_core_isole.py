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
