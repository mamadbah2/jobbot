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
    "je prépare votre CV et votre lettre, et je postule pour vous.\n"
    "Envoyez-moi votre CV pour commencer."
)

# --- /aide : toujours disponible (§11) --------------------------------------

AIDE: Final = (
    "*Comment ça marche*\n"
    "1. Vous envoyez votre CV (PDF ou Word).\n"
    "2. Vous vérifiez ce que j'ai compris de votre parcours.\n"
    "3. Vous choisissez vos secteurs et votre région.\n"
    "4. Vous recevez des offres, et je peux postuler à votre place.\n\n"
    "*Commandes*\n"
    "/start — revenir au début\n"
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
