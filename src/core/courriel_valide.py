"""Validation et normalisation des adresses email (CLAUDE.md §5).

`users.email` est unique : sans normalisation du domaine, `a@Example.sn` et
`a@example.sn` créeraient deux comptes pour la même boîte.

`check_deliverability=False` est délibéré : la vérification DNS est un appel
réseau. Elle rendrait les tests unitaires dépendants du réseau (interdit par
`tests/conftest.py`) et ferait échouer une inscription quand le VPS a un
souci de résolution — alors que l'adresse, elle, est bonne. Une adresse qui
n'existe pas se manifeste de toute façon par un code qui n'arrive jamais.
"""

from __future__ import annotations

from email_validator import EmailNotValidError, validate_email

from src.core.erreurs import AdresseInvalide


def normaliser(adresse: str) -> str:
    """Rend l'adresse normalisée, ou lève `AdresseInvalide`."""
    brut = adresse.strip()
    if not brut:
        raise AdresseInvalide("adresse_vide")

    try:
        resultat = validate_email(brut, check_deliverability=False)
    except EmailNotValidError as exc:
        raise AdresseInvalide("adresse_invalide") from exc

    return str(resultat.normalized)
