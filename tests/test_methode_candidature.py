"""Méthode de candidature déclarée par le recruteur (CLAUDE.md §2.1, §7).

WP Job Manager range la méthode dans `div.application_details`, hors de la
description. Quatre cas existent sur emploidakar et ils n'ont pas la même
conséquence produit :

- mailto          -> auto-submit possible
- lien externe    -> site tiers, souvent à login : mode brouillon OBLIGATOIRE (§2.1)
- formulaire local-> mode brouillon
- rien            -> on retombe sur l'email écrit dans la description
"""

from __future__ import annotations

from src.ingest.sources import emploidakar

DESC = '<div class="job_description">{}</div>'
BLOC = '<div class="application_details">{}</div>'


def test_mailto_du_bloc_donne_une_candidature_par_email() -> None:
    html = DESC.format("Poste ouvert.") + BLOC.format(
        '<a href="mailto:rh@societe.sn">Postuler</a>'
    )
    detail = emploidakar.parse_detail(html)
    assert detail.apply_email == "rh@societe.sn"
    assert detail.apply_method == "email"


def test_lien_externe_bascule_en_external_et_conserve_l_url() -> None:
    """§2.1 : jamais d'automatisation sur un site tiers à login."""
    html = DESC.format("Poste ouvert.") + BLOC.format(
        '<a href="https://careers.bakerhughes.com/job/R168668">Postuler</a>'
    )
    detail = emploidakar.parse_detail(html)
    assert detail.apply_method == "external"
    assert detail.apply_url == "https://careers.bakerhughes.com/job/R168668"
    assert detail.apply_email is None


def test_formulaire_du_portail_reste_en_mode_brouillon() -> None:
    html = DESC.format("Poste ouvert.") + BLOC.format(
        "<p>Prénom et noms</p><p>Télécharger votre CV</p>"
    )
    detail = emploidakar.parse_detail(html)
    assert detail.apply_method == "form"
    assert detail.apply_url is None


def test_sans_bloc_on_retombe_sur_l_email_de_la_description() -> None:
    html = DESC.format("Envoyez votre CV à recrutement@xyz.sn")
    detail = emploidakar.parse_detail(html)
    assert detail.apply_email == "recrutement@xyz.sn"
    assert detail.apply_method == "email"


def test_le_mailto_du_bloc_prime_sur_l_email_de_la_description() -> None:
    """Le bloc est renseigné par celui qui publie : c'est la consigne officielle."""
    html = DESC.format("Questions: info@xyz.sn") + BLOC.format(
        '<a href="mailto:recrutement@xyz.sn">Postuler</a>'
    )
    assert emploidakar.parse_detail(html).apply_email == "recrutement@xyz.sn"


def test_un_email_explicite_dans_la_description_l_emporte_sur_un_lien_externe() -> None:
    """Cas réel (CSS) : l'annonce dit « envoyer par mail » ET renvoie au site.

    Le recruteur a écrit l'adresse noir sur blanc : lui écrire est exactement
    ce qu'il demande, et c'est la seule voie où le produit apporte sa valeur.
    """
    html = DESC.format("A envoyer par mail à recrutement.rh@css.sn") + BLOC.format(
        '<a href="https://www.css.sn/poste/chef-de-parc/">Postuler</a>'
    )
    detail = emploidakar.parse_detail(html)
    assert detail.apply_method == "email"
    assert detail.apply_email == "recrutement.rh@css.sn"
    assert detail.apply_url == "https://www.css.sn/poste/chef-de-parc/"


def test_un_lien_vers_le_portail_lui_meme_n_est_pas_une_candidature_externe() -> None:
    html = DESC.format("Poste ouvert.") + BLOC.format(
        '<a href="https://www.emploidakar.com/mon-espace-candidat-3/">Postuler</a>'
    )
    detail = emploidakar.parse_detail(html)
    assert detail.apply_method == "form"
    assert detail.apply_url is None
