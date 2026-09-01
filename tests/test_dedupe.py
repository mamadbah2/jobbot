"""Dédoublonnage des offres (CLAUDE.md §5, colonne `jobs.fingerprint`).

La même annonce est souvent republiée sur plusieurs portails avec une casse,
des accents ou des espaces différents : l'empreinte doit les rapprocher.
"""

from __future__ import annotations

from src.ingest.dedupe import compute_fingerprint


def test_empreinte_stable_pour_la_meme_offre() -> None:
    a = compute_fingerprint("Chef de parc", "CSS", "Dakar")
    b = compute_fingerprint("Chef de parc", "CSS", "Dakar")
    assert a == b


def test_empreinte_insensible_a_la_casse_et_aux_espaces() -> None:
    a = compute_fingerprint("Chef de parc", "CSS", "Dakar")
    b = compute_fingerprint("  CHEF   DE  PARC ", "css", "DAKAR")
    assert a == b


def test_empreinte_insensible_aux_accents() -> None:
    """« sénior » et « senior » désignent le même poste."""
    assert compute_fingerprint("Animateur sénior", "RH", "Dakar") == compute_fingerprint(
        "Animateur senior", "RH", "Dakar"
    )


def test_empreintes_differentes_pour_des_postes_differents() -> None:
    a = compute_fingerprint("Chef de parc", "CSS", "Dakar")
    b = compute_fingerprint("Chef de projet", "CSS", "Dakar")
    assert a != b


def test_empreintes_differentes_pour_des_entreprises_differentes() -> None:
    a = compute_fingerprint("Chef de parc", "CSS", "Dakar")
    b = compute_fingerprint("Chef de parc", "Sonatel", "Dakar")
    assert a != b


def test_entreprise_ou_lieu_absent_ne_fait_pas_echouer() -> None:
    empreinte = compute_fingerprint("Chef de parc", None, None)
    assert isinstance(empreinte, str) and empreinte


def test_empreinte_tient_dans_la_colonne_varchar_64() -> None:
    """§5 : `jobs.fingerprint` est un VARCHAR(64)."""
    assert len(compute_fingerprint("Chef de parc", "CSS", "Dakar")) <= 64
