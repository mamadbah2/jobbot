"""Écran d'accueil : /start et /aide."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message, User

from src.bot import keyboards, texts
from src.logging_setup import get_logger

log = get_logger(__name__)
router = Router(name="start")


def _prenom(user: User | None) -> str:
    """Prénom Telegram, ou repli neutre si absent."""
    if user is not None and user.first_name:
        return user.first_name
    return "et bienvenue"


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    # Sert aussi à mesurer les abandons d'onboarding (§11).
    log.info("onboarding_etape", etape="start", telegram_id=message.chat.id)
    await message.answer(
        texts.START.format(prenom=_prenom(message.from_user)),
        reply_markup=keyboards.accueil(),
    )


@router.message(Command("aide"))
async def cmd_aide(message: Message) -> None:
    await message.answer(texts.AIDE, parse_mode="Markdown", reply_markup=keyboards.retour())


@router.callback_query(F.data == "nav:aide")
async def cb_aide(callback: CallbackQuery) -> None:
    # `callback.from_user` est bien l'utilisateur ; `callback.message.from_user`
    # serait le bot lui-même.
    if isinstance(callback.message, Message):
        await callback.message.answer(
            texts.AIDE, parse_mode="Markdown", reply_markup=keyboards.retour()
        )
    await callback.answer()


@router.callback_query(F.data == "nav:accueil")
async def cb_accueil(callback: CallbackQuery) -> None:
    if isinstance(callback.message, Message):
        await callback.message.answer(
            texts.START.format(prenom=_prenom(callback.from_user)),
            reply_markup=keyboards.accueil(),
        )
    await callback.answer()
