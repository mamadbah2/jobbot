"""TOUS les textes destinés à l'utilisateur (CLAUDE.md §4).

Règles : français simple, sans jargon RH, **vouvoiement partout** (§11),
messages courts car la data est chère et lente.
Aucun texte utilisateur ne doit apparaître ailleurs dans le code.
"""

from __future__ import annotations

from typing import Final

# --- /start : 3 lignes maximum (§6, onboarding) -----------------------------

START: Final = (
    "Bonjour {prenom} 👋\n"
    "Je trouve les offres d'emploi qui vous correspondent au Sénégal, "
    "et je prépare votre CV et votre lettre pour chacune.\n"
    "C'est vous qui déposez votre candidature — je vous dis où et comment."
)

# --- /aide : toujours disponible (§11) --------------------------------------

AIDE: Final = (
    "*Comment ça marche*\n"
    "1. Vous créez votre compte avec votre adresse email.\n"
    "2. Vous envoyez votre CV (PDF ou Word).\n"
    "3. Vous vérifiez ce que j'ai compris de votre parcours.\n"
    "4. Vous recevez des offres, avec un CV et une lettre prêts à déposer.\n\n"
    "Je ne postule jamais à votre place : je prépare tout, vous envoyez.\n\n"
    "*Commandes*\n"
    "/start — revenir au début\n"
    "/compte — lier ce Telegram à votre compte\n"
    "/aide — afficher ce message\n\n"
    "Un souci ? Répondez simplement à ce message."
)

# --- Boutons ----------------------------------------------------------------

BTN_ENVOYER_CV: Final = "📄 Envoyer mon CV"
BTN_AIDE: Final = "❓ Aide"
BTN_RETOUR: Final = "◀️ Retour"

# --- Erreurs ----------------------------------------------------------------

ERREUR_TECHNIQUE: Final = (
    "Un problème technique est survenu de mon côté. Réessayez dans quelques minutes."
)

# --- Liaison de compte -------------------------------------------------------

COMPTE_DEMANDER_CONTACT: Final = (
    "Pour retrouver votre compte, appuyez sur le bouton ci-dessous.\n"
    "Telegram me transmettra votre numéro, rien d'autre."
)

COMPTE_LIE: Final = (
    "C'est fait, ce Telegram est relié à votre compte.\n"
    "Vous recevrez ici les offres qui vous correspondent."
)

COMPTE_DEJA_LIE: Final = "Ce Telegram est déjà relié à votre compte."

COMPTE_INTROUVABLE: Final = (
    "Je ne trouve aucun compte avec ce numéro.\n"
    "Créez d'abord votre compte, puis revenez ici."
)

COMPTE_CONTACT_REFUSE: Final = (
    "Ce contact n'est pas le vôtre. Utilisez le bouton pour partager votre propre numéro."
)

COMPTE_TELEGRAM_DEJA_PRIS: Final = (
    "Ce compte Telegram est déjà relié à un autre compte JobBot.\n"
    "Si c'est une erreur, répondez à ce message."
)

BTN_PARTAGER_CONTACT: Final = "📱 Partager mon numéro"
