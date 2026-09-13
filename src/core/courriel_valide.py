"""Validation et normalisation des adresses email (CLAUDE.md §5).

`users.email` est unique : sans normalisation du domaine, `a@Example.sn` et
`a@example.sn` créeraient deux comptes pour la même boîte.

`check_deliverability=False` est délibéré : la vérification DNS est un appel
réseau. Elle rendrait les tests unitaires dépendants du réseau (interdit par
`tests/conftest.py`) et ferait échouer une inscription quand le VPS a un
souci de résolution — alors que l'adresse, elle, est bonne. Une adresse qui
n'existe pas se manifeste de toute façon par un code qui n'arrive jamais.

`LONGUEUR_MAX = 320` : c'est la taille de la colonne `users.email`
(`String(320)`) — une adresse plus longue serait de toute façon non
stockable. La borne coupe aussi court avant `validate_email()`, dont le coût
est quadratique en longueur d'entrée (`src/core/saisie.py`).
"""

from __future__ import annotations

from email_validator import EmailNotValidError, validate_email

from src.core.erreurs import AdresseInvalide
from src.core.saisie import texte_saisi

LONGUEUR_MAX = 320


def normaliser(adresse: str) -> str:
    """Rend l'adresse normalisée, ou lève `AdresseInvalide`."""
    brut = texte_saisi(
        adresse, longueur_max=LONGUEUR_MAX, erreur=AdresseInvalide, sujet="adresse"
    )

    try:
        resultat = validate_email(brut, check_deliverability=False)
    except EmailNotValidError as exc:
        raise AdresseInvalide("adresse_invalide") from exc

    return str(resultat.normalized)
