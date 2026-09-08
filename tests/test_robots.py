"""Lecture de robots.txt (CLAUDE.md §2 interdiction n°4, §7).

`urllib.robotparser` ne convient pas : sur le robots.txt réel d'emploidakar il
refuse `/wp-admin/admin-ajax.php` — pourtant explicitement autorisé, et notre
seul point d'entrée — et il autorise `/resume/` parce qu'il ignore les groupes
`User-agent: *` suivants. Les deux erreurs sont graves, d'où cette lecture.
"""

from __future__ import annotations

from src.ingest.robots import ReglesRobots

# Extrait fidèle du robots.txt réel d'emploidakar.com (relevé le 2026-09-01).
ROBOTS_EMPLOIDAKAR = """User-agent: *
Disallow: /wp-admin/
Allow: /wp-admin/admin-ajax.php

User-agent: *
Disallow: /wp-includes/

User-agent: *
Disallow: /wp-content/uploads/job_applications/

User-agent: *
Disallow: /resume/

User-agent: *
Disallow: /CV/

User-agent: MJ12bot
Disallow: /
"""

UA = "JobBotSN/0.1 (+contact: admin@example.sn)"


def _regles(texte: str = ROBOTS_EMPLOIDAKAR, ua: str = UA) -> ReglesRobots:
    return ReglesRobots.analyser(texte, ua)


def test_autorise_admin_ajax_malgre_le_disallow_du_repertoire() -> None:
    """Le cas dont dépend toute la source : Allow plus long que Disallow."""
    assert _regles().autorise("https://www.emploidakar.com/wp-admin/admin-ajax.php") is True


def test_interdit_le_reste_de_wp_admin() -> None:
    assert _regles().autorise("https://www.emploidakar.com/wp-admin/options.php") is False


def test_interdit_resume_declare_dans_un_groupe_ulterieur() -> None:
    """Piège de robotparser : les groupes `User-agent: *` suivants comptent aussi."""
    assert _regles().autorise("https://www.emploidakar.com/resume/quelquun") is False


def test_interdit_la_cvtheque_et_les_candidatures_deposees() -> None:
    regles = _regles()
    assert regles.autorise("https://www.emploidakar.com/CV/x") is False
    assert (
        regles.autorise("https://www.emploidakar.com/wp-content/uploads/job_applications/a.pdf")
        is False
    )


def test_autorise_une_page_d_annonce_normale() -> None:
    assert _regles().autorise("https://www.emploidakar.com/offre-demploi/chef-de-parc/") is True


def test_ignore_les_groupes_visant_un_autre_robot() -> None:
    """`Disallow: /` pour MJ12bot ne nous concerne pas."""
    assert _regles().autorise("https://www.emploidakar.com/") is True


def test_un_groupe_visant_notre_agent_l_emporte_sur_l_etoile() -> None:
    texte = "User-agent: *\nDisallow: /\n\nUser-agent: JobBotSN\nDisallow: /prive/\n"
    regles = _regles(texte)
    assert regles.autorise("https://s.sn/offres/") is True
    assert regles.autorise("https://s.sn/prive/x") is False


def test_robots_vide_autorise_tout() -> None:
    assert _regles("").autorise("https://s.sn/n-importe-quoi") is True


def test_disallow_vide_signifie_tout_autoriser() -> None:
    assert _regles("User-agent: *\nDisallow:\n").autorise("https://s.sn/x") is True


def test_supporte_l_ancre_de_fin_de_chaine() -> None:
    regles = _regles("User-agent: *\nDisallow: /*.pdf$\n")
    assert regles.autorise("https://s.sn/doc.pdf") is False
    assert regles.autorise("https://s.sn/doc.pdf.html") is True


def test_directives_insensibles_a_la_casse() -> None:
    regles = _regles("USER-AGENT: *\nDISALLOW: /prive/\n")
    assert regles.autorise("https://s.sn/prive/x") is False


def test_sur_le_robots_txt_reel_complet() -> None:
    """Fixture figée du fichier réel : plus de 20 groupes, pièges inclus."""
    from pathlib import Path

    texte = (Path(__file__).parent / "fixtures" / "emploidakar_robots.txt").read_text(
        encoding="utf-8"
    )
    regles = ReglesRobots.analyser(texte, UA)
    base = "https://www.emploidakar.com"
    assert regles.autorise(f"{base}/wp-admin/admin-ajax.php") is True
    assert regles.autorise(f"{base}/offre-demploi/chef-de-parc/") is True
    assert regles.autorise(f"{base}/resume/quelquun") is False
    assert regles.autorise(f"{base}/CV/quelquun") is False
    assert regles.autorise(f"{base}/wp-content/uploads/job_applications/a.pdf") is False


def test_un_motif_hostile_ne_fige_pas_le_worker() -> None:
    """Le robots.txt vient du site : il ne doit jamais pouvoir bloquer la passe.

    Avec une traduction naïve en regex, ce motif provoquait un recul
    catastrophique (facteur ~4 par caractère : 8 s à 30 caractères, plusieurs
    minutes à 34). Le worker tourne avec `max_instances=1` : il ne repartait
    jamais.
    """
    import time

    regles = ReglesRobots.analyser("User-agent: *\nDisallow: /" + "a*" * 20 + "b\n", UA)
    debut = time.monotonic()
    regles.autorise("https://s.sn/" + "a" * 36)
    assert time.monotonic() - debut < 1.0


def test_le_motif_hostile_reste_correctement_evalue() -> None:
    """La protection ne doit pas se payer par un résultat faux."""
    regles = ReglesRobots.analyser("User-agent: *\nDisallow: /aa*bb\n", UA)
    assert regles.autorise("https://s.sn/aaXXbbYY") is False
    assert regles.autorise("https://s.sn/aaXXcc") is True
