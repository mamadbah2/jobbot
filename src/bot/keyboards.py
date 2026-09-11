"""Claviers inline. Chaque écran propose une sortie (CLAUDE.md §11)."""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from src.bot import texts


def accueil() -> InlineKeyboardMarkup:
    """Clavier de l'écran /start."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN_ENVOYER_CV, callback_data="cv:envoyer")],
            [InlineKeyboardButton(text=texts.BTN_AIDE, callback_data="nav:aide")],
        ]
    )


def retour(destination: str = "nav:accueil") -> InlineKeyboardMarkup:
    """Clavier ne contenant qu'un bouton retour."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=texts.BTN_RETOUR, callback_data=destination)]]
    )


def partager_contact() -> ReplyKeyboardMarkup:
    """Bouton natif de partage de contact.

    Telegram ne renvoie par ce bouton que le numéro de l'utilisateur lui-même,
    et il l'a déjà vérifié : c'est ce qui rend la liaison gratuite et sûre (§9).
    """
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=texts.BTN_PARTAGER_CONTACT, request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
