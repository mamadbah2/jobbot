"""Claviers inline. Chaque écran propose une sortie (CLAUDE.md §11)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

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
