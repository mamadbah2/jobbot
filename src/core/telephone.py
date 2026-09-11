"""Normalisation des numéros de téléphone sénégalais (CLAUDE.md §5).

`users.phone` est unique et obligatoire : il sert d'une part à retrouver un compte
depuis le bouton « partager mon contact » de Telegram, d'autre part au paiement
mobile money (§10). Deux écritures d'un même numéro doivent donc produire la même
chaîne, sinon l'unicité ne protège rien et un utilisateur crée un doublon en
tapant « 77 123 45 67 » au lieu de « +221771234567 ».

Seul le Sénégal est accepté : Wave, Orange Money et Free Money le sont aussi.

`LONGUEUR_MAX = 64` : le format le plus verbeux qu'on accepte
(`+221 (77) 123-45-67`) fait 19 caractères ; 64 laisse toute la marge utile
sans ouvrir la porte à une saisie non bornée (`src/core/saisie.py`).
"""

from __future__ import annotations

import phonenumbers

from src.core.erreurs import NumeroInvalide
from src.core.saisie import texte_saisi

REGION = "SN"
LONGUEUR_MAX = 64


def normaliser(numero: str) -> str:
    """Rend le numéro au format E.164, ou lève `NumeroInvalide`."""
    brut = texte_saisi(numero, longueur_max=LONGUEUR_MAX, erreur=NumeroInvalide, sujet="numero")

    try:
        analyse = phonenumbers.parse(brut, REGION)
    except phonenumbers.NumberParseException as exc:
        raise NumeroInvalide("numero_illisible") from exc

    if not phonenumbers.is_valid_number(analyse):
        raise NumeroInvalide("numero_invalide")

    # `parse` avec une région de repli accepte un numéro étranger écrit en
    # international : on revérifie explicitement le pays.
    if phonenumbers.region_code_for_number(analyse) != REGION:
        raise NumeroInvalide("numero_hors_senegal")

    return phonenumbers.format_number(analyse, phonenumbers.PhoneNumberFormat.E164)
