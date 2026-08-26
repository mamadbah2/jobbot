"""Handlers de l'écran d'accueil."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from aiogram.types import Chat, Message, User

from src.bot import texts
from src.bot.handlers import build_router
from src.bot.handlers.start import _prenom, cmd_aide, cmd_start


def _message(prenom: str | None = "Awa") -> Message:
    expediteur = User(id=42, is_bot=False, first_name=prenom) if prenom is not None else None
    return Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=42, type="private"),
        from_user=expediteur,
        text="/start",
    )


def test_prenom_repli_si_absent() -> None:
    assert _prenom(None) == "et bienvenue"
    assert _prenom(User(id=1, is_bot=False, first_name="Awa")) == "Awa"


async def test_start_repond_avec_le_prenom(monkeypatch: pytest.MonkeyPatch) -> None:
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)

    await cmd_start(_message("Awa"))

    answer.assert_awaited_once()
    envoye = answer.await_args.args[0]
    assert "Awa" in envoye
    assert len(envoye.strip().splitlines()) <= 3


async def test_start_propose_une_action(monkeypatch: pytest.MonkeyPatch) -> None:
    """§11 : chaque écran propose une sortie."""
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)

    await cmd_start(_message())

    clavier = answer.await_args.kwargs["reply_markup"]
    libelles = [b.text for ligne in clavier.inline_keyboard for b in ligne]
    assert texts.BTN_ENVOYER_CV in libelles
    assert texts.BTN_AIDE in libelles


async def test_aide_repond(monkeypatch: pytest.MonkeyPatch) -> None:
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)

    await cmd_aide(_message())

    answer.assert_awaited_once()
    assert "/aide" in answer.await_args.args[0]


def test_router_racine_construit() -> None:
    router = build_router()
    assert router.name == "root"
    assert any(sous.name == "start" for sous in router.sub_routers)
