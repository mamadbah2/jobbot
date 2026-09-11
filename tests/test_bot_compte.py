"""Liaison de compte par « partager mon contact » (spec Phase 2 §9)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from aiogram.types import Chat, Contact, Message, ReplyKeyboardRemove, User

from src.bot import texts
from src.bot.handlers.compte import contact_recu, verifier_contact
from src.core.erreurs import CompteInexistant, ContactUsurpe, TelegramDejaLie


class FauxContact:
    def __init__(self, phone_number: str, user_id: int | None) -> None:
        self.phone_number = phone_number
        self.user_id = user_id


def test_contact_personnel_accepte() -> None:
    assert verifier_contact(FauxContact("+221771234567", 555), 555) == "+221771234567"


def test_contact_d_un_tiers_refuse() -> None:
    """Sans ce contrôle, on se greffe sur le compte de quelqu'un d'autre."""
    with pytest.raises(ContactUsurpe):
        verifier_contact(FauxContact("+221779999999", 999), 555)


def test_contact_sans_user_id_refuse() -> None:
    """Un contact saisi à la main n'a pas de user_id : rien ne le vérifie."""
    with pytest.raises(ContactUsurpe):
        verifier_contact(FauxContact("+221771234567", None), 555)


def _message_avec_contact(
    *, numero: str, contact_user_id: int | None, expediteur_id: int
) -> Message:
    expediteur = User(id=expediteur_id, is_bot=False, first_name="Awa")
    contact = Contact(phone_number=numero, first_name="Awa", user_id=contact_user_id)
    return Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=expediteur_id, type="private"),
        from_user=expediteur,
        contact=contact,
    )


class _FausseSession:
    """Session bidon : le handler ne fait rien d'autre que passer par
    `session_scope`, qu'on neutralise via monkeypatch dans chaque test."""


async def test_contact_usurpe_refuse_sans_toucher_la_base(monkeypatch: pytest.MonkeyPatch) -> None:
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)
    lier = AsyncMock(side_effect=AssertionError("ne doit pas être appelé"))
    monkeypatch.setattr("src.bot.handlers.compte.comptes.lier_telegram", lier)

    message = _message_avec_contact(numero="+221779999999", contact_user_id=999, expediteur_id=555)
    await contact_recu(message)

    answer.assert_awaited_once()
    assert answer.await_args.args[0] == texts.COMPTE_CONTACT_REFUSE
    assert isinstance(answer.await_args.kwargs["reply_markup"], ReplyKeyboardRemove)
    lier.assert_not_awaited()


async def test_compte_deja_lie_ne_relie_pas(monkeypatch: pytest.MonkeyPatch) -> None:
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)

    class _Utilisateur:
        id = 1

    monkeypatch.setattr(
        "src.bot.handlers.compte.comptes.par_telegram", AsyncMock(return_value=_Utilisateur())
    )
    lier = AsyncMock(side_effect=AssertionError("ne doit pas être appelé"))
    monkeypatch.setattr("src.bot.handlers.compte.comptes.lier_telegram", lier)

    class _FauxScope:
        async def __aenter__(self) -> _FausseSession:
            return _FausseSession()

        async def __aexit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr("src.bot.handlers.compte.session_scope", lambda: _FauxScope())

    message = _message_avec_contact(numero="+221771234567", contact_user_id=555, expediteur_id=555)
    await contact_recu(message)

    answer.assert_awaited_once()
    assert answer.await_args.args[0] == texts.COMPTE_DEJA_LIE
    lier.assert_not_awaited()


async def test_compte_introuvable(monkeypatch: pytest.MonkeyPatch) -> None:
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)
    monkeypatch.setattr(
        "src.bot.handlers.compte.comptes.par_telegram", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        "src.bot.handlers.compte.comptes.lier_telegram",
        AsyncMock(side_effect=CompteInexistant(CompteInexistant.code)),
    )

    class _FauxScope:
        async def __aenter__(self) -> _FausseSession:
            return _FausseSession()

        async def __aexit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr("src.bot.handlers.compte.session_scope", lambda: _FauxScope())

    message = _message_avec_contact(numero="+221771234567", contact_user_id=555, expediteur_id=555)
    await contact_recu(message)

    answer.assert_awaited_once()
    assert answer.await_args.args[0] == texts.COMPTE_INTROUVABLE


async def test_telegram_deja_pris_par_un_autre_compte(monkeypatch: pytest.MonkeyPatch) -> None:
    """Task 9 : `TelegramDejaLie` levée par `comptes.lier_telegram` — cas de
    course entre la vérification préalable et l'appel (comme `IntegrityError`
    dans `connecter_ou_inscrire`)."""
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)
    monkeypatch.setattr(
        "src.bot.handlers.compte.comptes.par_telegram", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        "src.bot.handlers.compte.comptes.lier_telegram",
        AsyncMock(side_effect=TelegramDejaLie(TelegramDejaLie.code)),
    )

    class _FauxScope:
        async def __aenter__(self) -> _FausseSession:
            return _FausseSession()

        async def __aexit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr("src.bot.handlers.compte.session_scope", lambda: _FauxScope())

    message = _message_avec_contact(numero="+221771234567", contact_user_id=555, expediteur_id=555)
    await contact_recu(message)

    answer.assert_awaited_once()
    assert answer.await_args.args[0] == texts.COMPTE_TELEGRAM_DEJA_PRIS
    assert isinstance(answer.await_args.kwargs["reply_markup"], ReplyKeyboardRemove)
