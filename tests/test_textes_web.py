"""Chaque erreur métier doit avoir une phrase dans le client web.

Sans ce test, le jour où quelqu'un ajoute une dixième erreur côté Python,
l'utilisateur verrait un message générique sans que personne ne s'en aperçoive.
C'est le seul lien vérifié entre les deux langages du dépôt.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.core.erreurs import ErreurMetier

TEXTES = Path("web/app/textes.ts")


def _codes_metier() -> set[str]:
    trouves: set[str] = set()

    def descendre(classe: type[ErreurMetier]) -> None:
        trouves.add(classe.code)
        for fille in classe.__subclasses__():
            descendre(fille)

    descendre(ErreurMetier)
    return trouves


def _codes_du_web() -> set[str]:
    source = TEXTES.read_text(encoding="utf-8")
    bloc = re.search(r"export const ERREURS[^{]*\{(.*?)\n\}", source, re.S)
    assert bloc, "le bloc ERREURS est introuvable dans textes.ts"
    return set(re.findall(r"^\s*([a-z_]+):", bloc.group(1), re.M))


def test_chaque_erreur_metier_a_une_phrase_dans_le_web() -> None:
    manquants = _codes_metier() - _codes_du_web()
    assert not manquants, f"codes sans texte utilisateur : {sorted(manquants)}"


def test_le_web_porte_un_message_par_defaut() -> None:
    """Un code inconnu ne doit jamais s'afficher tel quel à l'utilisateur."""
    assert "defaut" in _codes_du_web()
