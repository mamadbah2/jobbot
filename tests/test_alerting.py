"""Alerte administrateur (CLAUDE.md §7 : « ne jamais échouer en silence »).

Telegram portait ce canal jusqu'au 2026-09-12. Il passe à l'email, derrière le
même protocole `AlerteAdmin` : aucun appelant ne change.
"""

from __future__ import annotations

import pytest
from structlog.testing import capture_logs

from src.alerting import AlerteCourriel, AlerteJournalisee, construire_alerte
from src.config import get_settings


class FournisseurEspion:
    """Capture les messages, n'envoie rien."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str]] = []

    async def envoyer_code(self, destinataire: str, code: str) -> None:  # pragma: no cover
        raise AssertionError("une alerte ne doit jamais passer par envoyer_code")

    async def envoyer_message(self, destinataire: str, sujet: str, corps: str) -> None:
        self.messages.append((destinataire, sujet, corps))


class FournisseurEnPanne:
    async def envoyer_code(self, destinataire: str, code: str) -> None:  # pragma: no cover
        raise AssertionError("non sollicité")

    async def envoyer_message(self, destinataire: str, sujet: str, corps: str) -> None:
        raise RuntimeError("smtp injoignable")


async def test_journalise_l_alerte_en_erreur() -> None:
    with capture_logs() as journal:
        await AlerteJournalisee().envoyer("scraper_casse", source="x")
    (evenement,) = journal
    assert evenement["log_level"] == "error"
    assert evenement["alerte"] == "scraper_casse"
    assert evenement["source"] == "x"
    assert evenement["canal"] == "log_uniquement_admin_non_configure"


async def test_l_alerte_courriel_part_par_le_fournisseur() -> None:
    espion = FournisseurEspion()
    with capture_logs() as journal:
        await AlerteCourriel("admin@jobbot.sn", espion).envoyer(
            "scraper_casse", source="emploidakar", offres=0
        )
    (destinataire, sujet, corps) = espion.messages[0]
    assert destinataire == "admin@jobbot.sn"
    assert "scraper_casse" in sujet
    assert "emploidakar" in corps
    assert "offres : 0" in corps
    # L'alerte reste tracée dans les logs du VPS même quand elle part par email :
    # le fichier de logs est le seul historique consultable après coup.
    assert journal[0]["alerte"] == "scraper_casse"
    assert journal[0]["canal"] == "courriel"


async def test_une_panne_d_envoi_ne_remonte_pas_a_l_appelant() -> None:
    """L'appelant est au milieu d'un chemin d'erreur : il ne peut rien faire de
    cette exception, et une alerte qui explose en signalant un incident
    aggrave l'incident."""
    with capture_logs() as journal:
        await AlerteCourriel("admin@jobbot.sn", FournisseurEnPanne()).envoyer("scraper_casse")
    evenements = [e["event"] for e in journal]
    assert "alerte_admin" in evenements
    assert "alerte_admin_envoi_echoue" in evenements


def test_la_fabrique_choisit_le_courriel_quand_une_adresse_est_configuree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ADMIN_COURRIEL", "admin@jobbot.sn")
    get_settings.cache_clear()
    alerte = construire_alerte(get_settings())
    assert isinstance(alerte, AlerteCourriel)
    assert alerte.destinataire == "admin@jobbot.sn"


def test_la_fabrique_retombe_sur_le_log_sans_adresse() -> None:
    """Sans destinataire, on ne peut que journaliser — et le dire dans
    l'événement, pour ne pas croire l'alerte transmise."""
    get_settings.cache_clear()
    assert get_settings().admin_courriel == ""
    assert isinstance(construire_alerte(get_settings()), AlerteJournalisee)


def test_le_reglage_telegram_de_l_admin_n_existe_plus() -> None:
    from src.config import Settings

    assert "admin_telegram_id" not in Settings.model_fields
