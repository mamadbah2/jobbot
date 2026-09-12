"""Garde anti-retour du retrait du 2026-09-12.

Telegram et le numéro de téléphone ont été retirés du produit (spec
`docs/superpowers/specs/2026-09-12-retrait-telegram-design.md`). Sans ces
tests, ils peuvent revenir par un import isolé, un réglage rajouté ou une
fonction ressuscitée, sans que rien ne le signale : c'est précisément ce
genre de retour silencieux qu'aucun test fonctionnel ne voit.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

RACINE_SRC = Path("src")


def _fichiers_src() -> list[Path]:
    fichiers = sorted(RACINE_SRC.rglob("*.py"))
    assert len(fichiers) >= 30, "arborescence src/ introuvable : le test serait creux"
    return fichiers


def _modules_importes(fichier: Path) -> set[str]:
    arbre = ast.parse(fichier.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module and noeud.level == 0:
            modules.add(noeud.module.split(".")[0])
    return modules


def test_aucun_module_de_src_n_importe_aiogram() -> None:
    fautifs = [str(f) for f in _fichiers_src() if "aiogram" in _modules_importes(f)]
    assert not fautifs, f"aiogram est de retour dans : {fautifs}"


def test_aiogram_n_est_plus_une_dependance_declaree() -> None:
    """Retirer les imports sans retirer la dépendance laisserait l'image Docker
    la télécharger et un futur import passer inaperçu."""
    projet = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    declarees = " ".join(projet["project"]["dependencies"]).lower()
    assert "aiogram" not in declarees


def test_le_paquet_du_bot_n_existe_plus() -> None:
    assert not Path("src/bot").exists(), "src/bot/ est de retour"


def test_l_usage_de_cle_liaison_n_existe_plus() -> None:
    """`cles.Usage` est un `Literal` : mypy seul le contrôle, et mypy ne tourne
    pas en CI de test. Sans cette assertion, `deriver(secret, "liaison")`
    resterait écrivable à l'exécution."""
    from typing import get_args

    from src.core.auth import cles

    assert "liaison" not in get_args(cles.Usage)


def test_aucun_reglage_de_liaison_telegram() -> None:
    from src.config import Settings

    assert "telegram_bot_username" not in Settings.model_fields


def test_le_module_de_normalisation_telephonique_n_existe_plus() -> None:
    assert not Path("src/core/telephone.py").exists()


def test_phonenumbers_n_est_plus_une_dependance_declaree() -> None:
    projet = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    declarees = " ".join(projet["project"]["dependencies"]).lower()
    assert "phonenumbers" not in declarees


def test_les_fonctions_telephone_et_telegram_ont_disparu_des_comptes() -> None:
    """Elles portaient la pose d'un numéro et la liaison d'un telegram_id sur un
    compte. Les ressusciter sans colonne les ferait échouer à l'exécution, pas
    à l'import : cette assertion est ce qui rend le retrait visible."""
    from src.core.auth import comptes

    for nom in ("par_telephone", "par_telegram", "lier_telegram", "definir_telephone"):
        assert not hasattr(comptes, nom), f"comptes.{nom} est de retour"


def test_les_exceptions_du_telephone_et_de_telegram_ont_disparu() -> None:
    from src.core import erreurs

    for nom in ("NumeroInvalide", "TelephoneDejaUtilise", "ContactUsurpe", "TelegramDejaLie"):
        assert not hasattr(erreurs, nom), f"erreurs.{nom} est de retour"
        assert nom not in erreurs.__all__
