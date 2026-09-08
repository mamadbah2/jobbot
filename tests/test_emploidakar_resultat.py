"""`parse_list` doit rendre compte de ce qu'il a écarté (CLAUDE.md §7)."""

from __future__ import annotations

import json
from pathlib import Path

from src.ingest.sources import emploidakar

FIXTURES = Path(__file__).parent / "fixtures"


def test_compte_les_offres_ignorees() -> None:
    """Un <li> sans titre est écarté, mais il doit être compté."""
    payload = {
        "max_num_pages": 1,
        "html": (
            '<li class="job_listing post-1"><a href="https://x/a"><h3>Bon</h3></a></li>'
            '<li class="job_listing post-2"><a href="https://x/b"></a></li>'
        ),
    }
    resultat = emploidakar.parse_list(payload)
    assert [o.source_id for o in resultat.offres] == ["1"]
    assert resultat.ignorees == 1


def test_aucune_offre_ignoree_sur_la_fixture_reelle() -> None:
    payload = json.loads((FIXTURES / "emploidakar_listings.json").read_text(encoding="utf-8"))
    resultat = emploidakar.parse_list(payload)
    assert len(resultat.offres) == 17
    assert resultat.ignorees == 0
