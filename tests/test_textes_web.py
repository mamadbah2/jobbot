"""Chaque erreur métier doit avoir une phrase dans le client web.

Sans ce test, le jour où quelqu'un ajoute une dixième erreur côté Python,
l'utilisateur verrait un message générique sans que personne ne s'en aperçoive.
C'est le seul lien vérifié entre les deux langages du dépôt.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.api.schemas.profil import CorrectionProfil
from src.core.erreurs import ErreurMetier

TEXTES = Path("web/app/textes.ts")
CONTRAT = Path("web/app/api-contrat.ts")


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



def _limites_du_web() -> dict[str, int]:
    source = CONTRAT.read_text(encoding="utf-8")
    bloc = re.search(r"export const LIMITES_LISTES = \{(.*?)\n\}", source, re.S)
    assert bloc, "le bloc LIMITES_LISTES est introuvable dans api-contrat.ts"
    return {cle: int(valeur) for cle, valeur in re.findall(r"(\w+): (\d+)", bloc.group(1))}


def _limites_du_schema() -> dict[str, int]:
    """Lues sur le schéma lui-même, pas sur la constante : c'est ce que l'API
    APPLIQUE qui fait foi, pas ce qu'un commentaire annonce."""
    limites: dict[str, int] = {}
    for nom, champ in CorrectionProfil.model_fields.items():
        # Seules les LISTES : `max_length` borne aussi la longueur des chaînes,
        # qui n'a rien à voir et que l'écran n'a pas à connaître.
        if champ.annotation != list[str]:
            continue
        for contrainte in champ.metadata:
            longueur = getattr(contrainte, "max_length", None)
            if longueur is not None:
                limites[nom] = longueur
    return limites


def test_les_plafonds_de_listes_sont_les_memes_des_deux_cotes() -> None:
    """Sinon l'écran laisse passer ce que l'API refuse, par un 422 de pydantic
    sans code d'erreur — et l'utilisateur ne peut plus jamais enregistrer son
    profil sans savoir pourquoi (revue finale, I-2)."""
    assert _limites_du_schema() == _limites_du_web()
