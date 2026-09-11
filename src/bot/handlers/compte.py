"""Liaison du compte depuis Telegram (spec Phase 2 §9).

Telegram ne partage pas d'adresse email, mais son bouton natif « partager mon
contact » renvoie le numéro de l'utilisateur, DÉJÀ VÉRIFIÉ par Telegram. Comme
`users.phone` est unique et obligatoire, ce numéro suffit à retrouver le compte :
la liaison ne coûte aucun email.

Le garde-fou tient en une ligne et il est indispensable : un contact peut être
TRANSFÉRÉ. Sans `contact.user_id == message.from_user.id`, n'importe qui
transmettrait le contact d'un tiers et se grefferait sur son compte.
"""

from __future__ import annotations

from typing import Protocol

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardRemove

from src.bot import keyboards, texts
from src.core.auth import comptes
from src.core.erreurs import CompteInexistant, ContactUsurpe, NumeroInvalide, TelegramDejaLie
from src.db.session import session_scope
from src.logging_setup import get_logger

log = get_logger(__name__)
router = Router(name="compte")


class ContactPartage(Protocol):
    """Le strict minimum de `aiogram.types.Contact` dont on a besoin."""

    phone_number: str
    user_id: int | None


def verifier_contact(contact: ContactPartage, expediteur_id: int) -> str:
    """Rend le numéro si le contact appartient bien à l'expéditeur."""
    if contact.user_id is None or contact.user_id != expediteur_id:
        raise ContactUsurpe(ContactUsurpe.code)
    return contact.phone_number


@router.message(Command("compte"))
async def cmd_compte(message: Message) -> None:
    await message.answer(
        texts.COMPTE_DEMANDER_CONTACT, reply_markup=keyboards.partager_contact()
    )


@router.message(F.contact)
async def contact_recu(message: Message) -> None:
    if message.contact is None or message.from_user is None:
        return

    try:
        numero = verifier_contact(message.contact, message.from_user.id)
    except ContactUsurpe:
        # `message.from_user.id` est l'identifiant de l'attaquant présumé, pas
        # de la victime : le journaliser permet de corréler des tentatives
        # répétées, sans exposer le numéro (donnée personnelle, §14.4).
        log.warning("contact_usurpe", telegram_id=message.from_user.id)
        await message.answer(
            texts.COMPTE_CONTACT_REFUSE, reply_markup=ReplyKeyboardRemove()
        )
        return

    async with session_scope() as session:
        deja = await comptes.par_telegram(session, message.from_user.id)
        if deja is not None:
            await message.answer(texts.COMPTE_DEJA_LIE, reply_markup=ReplyKeyboardRemove())
            return
        try:
            utilisateur = await comptes.lier_telegram(
                session, telephone_saisi=numero, telegram_id=message.from_user.id
            )
        except CompteInexistant:
            await message.answer(
                texts.COMPTE_INTROUVABLE, reply_markup=ReplyKeyboardRemove()
            )
            return
        except TelegramDejaLie:
            log.warning("telegram_deja_lie")
            await message.answer(
                texts.COMPTE_TELEGRAM_DEJA_PRIS, reply_markup=ReplyKeyboardRemove()
            )
            return
        except NumeroInvalide:
            # Numéro étranger (diaspora, SIM malienne/ivoirienne...) : §7,
            # ne jamais échouer en silence.
            await message.answer(
                texts.COMPTE_NUMERO_ETRANGER, reply_markup=ReplyKeyboardRemove()
            )
            return

    log.info("compte_lie_telegram", user_id=utilisateur.id)
    await message.answer(texts.COMPTE_LIE, reply_markup=ReplyKeyboardRemove())
