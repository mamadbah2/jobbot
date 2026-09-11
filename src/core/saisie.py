"""Contrôles communs à toute saisie utilisateur qui entre dans `core`.

`core` est la frontière de confiance de tout le projet : les annotations de
type ne protègent rien à l'exécution (un appelant peut toujours envoyer
`None`, un entier, une liste), et une entrée non bornée en longueur atteint
des validateurs au coût quadratique (mesuré sur `email_validator` : 0,22 s
pour 100 000 caractères, 2,48 s pour 400 000). Sans ce contrôle, une saisie
malveillante remonte en `AttributeError` (donc 500) au lieu d'une erreur
métier propre, et quelques centaines de Ko dans un corps de requête suffisent
à bloquer un thread plusieurs secondes sur l'endpoint public de la tâche 12.
"""

from __future__ import annotations

from src.core.erreurs import ErreurMetier


def texte_saisi(
    valeur: object,
    *,
    longueur_max: int,
    erreur: type[ErreurMetier],
    sujet: str,
) -> str:
    """Contrôles communs à toute saisie utilisateur qui entre dans `core`.

    `core` est la frontière de confiance : les annotations de type ne
    s'appliquent pas à l'exécution, et une entrée non bornée atteint des
    validateurs au coût quadratique.
    """
    if not isinstance(valeur, str):
        raise erreur(f"{sujet}_invalide")
    if len(valeur) > longueur_max:
        raise erreur(f"{sujet}_trop_long")
    nettoye = valeur.strip()
    if not nettoye:
        raise erreur(f"{sujet}_vide")
    return nettoye
