"""Politique de pagination incrémentale (CLAUDE.md §7).

Le worker tourne toutes les 2 h. Rouvrir les 238 annonces à chaque passe
coûterait 17 min et 238 requêtes chez un tiers, pour ~2 offres nouvelles.
On descend donc les pages jusqu'à retomber sur du déjà-connu.
"""

from __future__ import annotations

from src.ingest.base import RawJob
from src.ingest.pagination import analyser_page


def _offre(source_id: str) -> RawJob:
    return RawJob(source="emploidakar", source_id=source_id, url=f"u/{source_id}", title="t")


def test_toutes_les_offres_sont_nouvelles_quand_la_base_est_vide() -> None:
    decision = analyser_page([_offre("3"), _offre("2")], ids_connus=set())
    assert [o.source_id for o in decision.nouvelles] == ["3", "2"]
    assert decision.continuer is True


def test_ne_retient_que_les_offres_inconnues() -> None:
    decision = analyser_page([_offre("3"), _offre("2")], ids_connus={"2"})
    assert [o.source_id for o in decision.nouvelles] == ["3"]


def test_continue_tant_qu_une_offre_de_la_page_est_nouvelle() -> None:
    """Une seule nouveauté suffit : la page suivante peut en contenir d'autres."""
    decision = analyser_page([_offre("3"), _offre("2")], ids_connus={"2"})
    assert decision.continuer is True


def test_s_arrete_quand_la_page_entiere_est_deja_connue() -> None:
    """Signal d'arrêt : une page entièrement connue, pas une seule offre connue.

    Une annonce remontée en tête par le site ne doit pas stopper la passe.
    """
    decision = analyser_page([_offre("3"), _offre("2")], ids_connus={"2", "3"})
    assert decision.nouvelles == ()
    assert decision.continuer is False


def test_s_arrete_sur_une_page_vide() -> None:
    decision = analyser_page([], ids_connus={"1"})
    assert decision.continuer is False


def test_ne_stoppe_pas_sur_une_offre_connue_isolee_en_tete() -> None:
    """Cas réel : une offre « featured » republiée en haut de liste."""
    page = [_offre("9"), _offre("8"), _offre("7")]
    decision = analyser_page(page, ids_connus={"9"})
    assert [o.source_id for o in decision.nouvelles] == ["8", "7"]
    assert decision.continuer is True


def test_deduplique_les_ids_repetes_dans_une_meme_page() -> None:
    """La dérive de pagination peut renvoyer deux fois la même offre."""
    decision = analyser_page([_offre("5"), _offre("5")], ids_connus=set())
    assert [o.source_id for o in decision.nouvelles] == ["5"]
