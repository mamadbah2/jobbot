"""Liaison de compte par « partager mon contact » (spec Phase 2 §9)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from aiogram.types import Chat, Contact, Message, ReplyKeyboardRemove, User

from src.bot import texts
from src.bot.handlers.compte import contact_recu, verifier_contact
from src.core.erreurs import CompteInexistant, ContactUsurpe, NumeroInvalide, TelegramDejaLie


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


class _FauxScope:
    """Contexte async bidon substitué à `session_scope` dans les tests de
    handler : seul le comportement de `comptes.*` (monkeypatché à côté)
    compte, pas une vraie transaction."""

    async def __aenter__(self) -> _FausseSession:
        return _FausseSession()

    async def __aexit__(self, *exc: object) -> None:
        return None


def _patch_session_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.bot.handlers.compte.session_scope", lambda: _FauxScope())


class _SessionInstrumentee:
    """Session bidon qui compte les appels à `execute`, pour prouver qu'un
    chemin donné n'a jamais touché la base (round de correction 2). Si le
    code testé finit par y toucher quand même, on le veut explicite plutôt
    que masqué par une `AttributeError` sur une méthode absente."""

    def __init__(self) -> None:
        self.appels_execute = 0

    async def execute(self, *args: object, **kwargs: object) -> object:
        self.appels_execute += 1
        raise AssertionError("la session ne doit pas être sollicitée pour ce chemin")


class _ScopeInstrumente:
    """Comme `_FauxScope`, mais garde la session créée accessible depuis
    l'extérieur du `async with`, pour vérifier après coup qu'elle n'a pas
    été sollicitée."""

    def __init__(self) -> None:
        self.session = _SessionInstrumentee()

    async def __aenter__(self) -> _SessionInstrumentee:
        return self.session

    async def __aexit__(self, *exc: object) -> None:
        return None


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
    _patch_session_scope(monkeypatch)

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
    _patch_session_scope(monkeypatch)

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
    _patch_session_scope(monkeypatch)

    message = _message_avec_contact(numero="+221771234567", contact_user_id=555, expediteur_id=555)
    await contact_recu(message)

    answer.assert_awaited_once()
    assert answer.await_args.args[0] == texts.COMPTE_TELEGRAM_DEJA_PRIS
    assert isinstance(answer.await_args.kwargs["reply_markup"], ReplyKeyboardRemove)


async def test_numero_etranger_recoit_une_reponse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Round de correction 1 : documente la branche `except NumeroInvalide`
    en simulant directement `comptes.lier_telegram`. Ne prouve que
    l'existence du `except`, pas que le cas se produit réellement — c'est
    `test_numero_etranger_normalisation_reelle_ne_touche_pas_la_base`
    ci-dessous, par la vraie chaîne, qui fait foi (round de correction 2)."""
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)
    monkeypatch.setattr(
        "src.bot.handlers.compte.comptes.par_telegram", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        "src.bot.handlers.compte.comptes.lier_telegram",
        AsyncMock(side_effect=NumeroInvalide("numero_hors_senegal")),
    )
    _patch_session_scope(monkeypatch)

    message = _message_avec_contact(numero="+33612345678", contact_user_id=555, expediteur_id=555)
    await contact_recu(message)

    answer.assert_awaited_once()
    assert answer.await_args.args[0] == texts.COMPTE_NUMERO_ETRANGER
    assert isinstance(answer.await_args.kwargs["reply_markup"], ReplyKeyboardRemove)


@pytest.mark.parametrize(
    "numero",
    ["+33612345678", "223701234567"],
    ids=["hors_senegal", "invalide_sans_indicatif_senegalais"],
)
async def test_numero_etranger_normalisation_reelle_ne_touche_pas_la_base(
    monkeypatch: pytest.MonkeyPatch, numero: str
) -> None:
    """Round de correction 2 : la vraie chaîne, pas une simulation.

    `comptes.lier_telegram` n'est PAS mocké : on le laisse appeler
    `par_telephone`, qui appelle `telephone.normaliser(numero)` avant même de
    construire la requête. `+33612345678` (français, donc valide mais hors
    Sénégal) et `223701234567` (malien, sans le `+`, donc invalide pour
    `phonenumbers` avec la région de repli SN) empruntent deux chemins
    d'erreur différents dans `telephone.normaliser` (`numero_hors_senegal`
    contre `numero_invalide`), mais doivent produire la même réponse
    utilisateur.

    `comptes.par_telegram` (le contrôle « déjà lié », sans rapport avec la
    normalisation du numéro) reste mocké : c'est ce qui permet d'affirmer que
    le seul appel restant sur la session bidon serait celui de
    `par_telephone`, et que `telephone.normaliser` l'empêche d'avoir lieu.
    `_SessionInstrumentee.appels_execute == 0` est la preuve : le refus vient
    de la normalisation, pas d'un aller-retour en base.
    """
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)
    monkeypatch.setattr(
        "src.bot.handlers.compte.comptes.par_telegram", AsyncMock(return_value=None)
    )
    scope = _ScopeInstrumente()
    monkeypatch.setattr("src.bot.handlers.compte.session_scope", lambda: scope)

    message = _message_avec_contact(numero=numero, contact_user_id=555, expediteur_id=555)
    await contact_recu(message)  # ne doit lever aucune exception

    answer.assert_awaited_once()
    assert answer.await_args.args[0] == texts.COMPTE_NUMERO_ETRANGER
    assert isinstance(answer.await_args.kwargs["reply_markup"], ReplyKeyboardRemove)
    assert scope.session.appels_execute == 0
