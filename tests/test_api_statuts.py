"""Chaque erreur métier a un statut HTTP explicite.

`_STATUTS.get(type(exc), 400)` résout par type EXACT : une sous-classe absente
de la table retombe silencieusement sur 400, avec un corps de réponse pourtant
correct, donc sans que personne le voie. Ce trou a déjà mordu deux fois.
"""

from __future__ import annotations

from src.api.app import _STATUTS
from src.core.erreurs import ErreurMetier


def _toutes(classe: type[ErreurMetier]) -> set[type[ErreurMetier]]:
    trouvees: set[type[ErreurMetier]] = set()
    for fille in classe.__subclasses__():
        trouvees.add(fille)
        trouvees |= _toutes(fille)
    return trouvees


def test_chaque_erreur_metier_a_un_statut_explicite() -> None:
    manquantes = sorted(c.__name__ for c in _toutes(ErreurMetier) if c not in _STATUTS)
    assert not manquantes, f"sans statut dans _STATUTS : {manquantes}"
