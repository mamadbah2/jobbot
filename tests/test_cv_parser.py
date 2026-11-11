"""Parsing d'un CV : texte ou image → profil structuré + transcription.

Aucun appel réseau : la fonction d'appel est injectée. Un test unitaire qui
sortirait sur le réseau violerait l'en-tête de `tests/conftest.py`.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

import pytest
from structlog.testing import capture_logs

from src.core.erreurs import CvIllisible, CvPasUnCv
from src.llm.client import CoutAppel
from src.llm.cv_parser import VERSION_PROMPT_CV, analyser_cv
from src.llm.prompts import TEMPERATURE_CV

COUT = CoutAppel(0, 100, 50, Decimal("0.0001"))

PROFIL_VALIDE: dict[str, Any] = {
    "nom_complet": "Awa Diop",
    "titre": "Comptable",
    "telephone": "+221771234567",
    "experiences": [{"entreprise": "Alpha SARL", "poste": "Comptable", "periode": "2019-2024"}],
    "formations": [{"etablissement": "UCAD", "diplome": "Licence", "annee": "2018"}],
    "competences": ["SAGE", "Excel"],
    "langues": ["français", "wolof"],
    "secteurs_vises": [],
    "mobilite": None,
    "pretention_salariale": None,
    "est_un_cv": True,
    "transcription": "Awa Diop — Comptable — Alpha SARL 2019-2024 — UCAD Licence 2018",
}


def _appel(contenu: str) -> Callable[..., Awaitable[tuple[str, CoutAppel]]]:
    async def appeler(messages: Any, **_: Any) -> tuple[str, CoutAppel]:
        return contenu, COUT

    return appeler


async def test_analyse_un_cv_texte() -> None:
    profil, transcription, cout = await analyser_cv(
        texte="Awa Diop, comptable", appeler=_appel(json.dumps(PROFIL_VALIDE))
    )
    assert profil["nom_complet"] == "Awa Diop"
    assert "transcription" not in profil  # séparée du profil structuré
    assert "Awa Diop" in transcription
    assert cout.cout_usd == Decimal("0.0001")


async def test_nettoie_les_clotures_de_code() -> None:
    """Le modèle entoure souvent son JSON de ``` : §9 impose un parsing défensif."""
    enrobe = "```json\n" + json.dumps(PROFIL_VALIDE) + "\n```"
    profil, _, _ = await analyser_cv(texte="x", appeler=_appel(enrobe))
    assert profil["titre"] == "Comptable"


async def test_relance_une_fois_sur_un_json_invalide() -> None:
    """§9 : retry une fois en cas d'échec de lecture, pas zéro, pas trois."""
    essais: list[int] = []

    async def appeler(messages: Any, **_: Any) -> tuple[str, CoutAppel]:
        essais.append(1)
        if len(essais) == 1:
            return "ceci n'est pas du json", COUT
        return json.dumps(PROFIL_VALIDE), COUT

    profil, _, cout = await analyser_cv(texte="x", appeler=appeler)
    assert len(essais) == 2
    assert profil["nom_complet"] == "Awa Diop"
    # Les deux appels ont été payés : le coût rendu les additionne.
    assert cout.cout_usd == Decimal("0.0002")
    assert cout.tokens_entree_frais == 200


async def test_abandonne_apres_la_relance() -> None:
    essais: list[int] = []

    async def appeler(messages: Any, **_: Any) -> tuple[str, CoutAppel]:
        essais.append(1)
        return "toujours pas du json", COUT

    with pytest.raises(CvIllisible):
        await analyser_cv(texte="x", appeler=appeler)
    assert len(essais) == 2


async def test_refuse_un_json_bien_forme_mais_de_mauvaise_forme() -> None:
    """`structured` est la source de vérité du post-contrôle anti-invention de
    la Phase 5 (§8.5). Y laisser entrer une forme fausse ferait échouer ce
    contrôle plus tard, loin de sa cause."""
    mauvais = dict(PROFIL_VALIDE, experiences="Alpha SARL puis Beta")  # chaîne, pas liste
    with pytest.raises(CvIllisible):
        await analyser_cv(texte="x", appeler=_appel(json.dumps(mauvais)))

    sans_cle = {k: v for k, v in PROFIL_VALIDE.items() if k != "competences"}
    with pytest.raises(CvIllisible):
        await analyser_cv(texte="x", appeler=_appel(json.dumps(sans_cle)))


async def test_analyse_une_image() -> None:
    """Une photo part en base64 au modèle multimodal, sans extraction locale."""
    recu: dict[str, object] = {}

    async def appeler(messages: Any, **_: Any) -> tuple[str, CoutAppel]:
        recu["messages"] = messages
        return json.dumps(PROFIL_VALIDE), COUT

    await analyser_cv(image=b"\xff\xd8\xff binaire", type_image="jpeg", appeler=appeler)
    envoye = json.dumps(recu["messages"])
    assert "image_url" in envoye
    assert "data:image/jpeg;base64," in envoye


async def test_le_prompt_porte_une_version_et_interdit_dinventer() -> None:
    """§8.5 : la règle « jamais d'invention » est répétée dans chaque prompt."""
    recu: dict[str, object] = {}

    async def appeler(messages: Any, **_: Any) -> tuple[str, CoutAppel]:
        recu["messages"] = messages
        return json.dumps(PROFIL_VALIDE), COUT

    await analyser_cv(texte="x", appeler=appeler)
    systeme = json.dumps(recu["messages"]).lower()
    assert "n'inventes rien" in systeme or "jamais inventer" in systeme
    assert VERSION_PROMPT_CV


async def test_un_cv_en_anglais_est_analyse_et_non_refuse() -> None:
    """Les postes ONG et international, que le §7 cite comme un gisement,
    arrivent en anglais. Le parser ne doit pas les écarter."""
    anglais = dict(PROFIL_VALIDE, nom_complet="John Mensah", langues=["english", "french"])
    profil, _, _ = await analyser_cv(
        texte="John Mensah — Accountant — 8 years experience",
        appeler=_appel(json.dumps(anglais)),
    )
    assert profil["nom_complet"] == "John Mensah"


async def test_la_reponse_du_modele_ne_fuit_ni_en_journal_ni_en_exception() -> None:
    """Règle n°1 de la phase : le texte d'un CV n'atteint jamais un journal ni
    une exception. La réponse illisible contient ici un marqueur identifiable."""
    marqueur = "SECRET-MARQUEUR-CV"
    with capture_logs() as journal, pytest.raises(CvIllisible) as info:
        await analyser_cv(texte=marqueur, appeler=_appel(f"{marqueur} pas du json"))

    # Sans cette assertion le test passerait si rien n'était journalisé.
    assert journal, "le test ne voit aucun journal : il ne prouve rien"
    assert marqueur not in str(journal)
    assert info.value.__context__ is None  # JSONDecodeError.doc porte la réponse
    assert info.value.__cause__ is None


async def test_la_temperature_du_brief_arrive_jusqu_a_lappel() -> None:
    recues: list[object] = []

    async def appeler(messages: Any, **options: Any) -> tuple[str, CoutAppel]:
        recues.append(options.get("temperature"))
        return json.dumps(PROFIL_VALIDE), COUT

    await analyser_cv(texte="x", appeler=appeler)
    assert TEMPERATURE_CV == 0.3  # §9
    assert recues == [0.3]


@pytest.mark.parametrize(
    ("champ", "valeur"),
    [
        ("experiences", ["Alpha SARL"]),
        ("experiences", [{"entreprise": "Alpha SARL"}]),  # sans poste
        ("formations", [{"etablissement": "UCAD"}]),  # sans diplôme
        ("experiences", [{"entreprise": 3, "poste": "Comptable"}]),
        ("formations", ["Licence"]),
        ("formations", [{"etablissement": "UCAD", "diplome": 3}]),
        ("competences", [{"nom": "SAGE"}]),
        ("experiences", [{"entreprise": "A", "poste": "B", "periode": 2019}]),
    ],
)
async def test_la_validation_descend_dans_les_elements(champ: str, valeur: object) -> None:
    mauvais = dict(PROFIL_VALIDE, **{champ: valeur})
    with pytest.raises(CvIllisible):
        await analyser_cv(texte="x", appeler=_appel(json.dumps(mauvais)))


async def test_le_cout_des_deux_appels_est_porte_par_lechec() -> None:
    """Deux appels payés ne doivent pas disparaître quand on abandonne."""
    with pytest.raises(CvIllisible) as info:
        await analyser_cv(texte="x", appeler=_appel("pas du json"))
    assert info.value.cout == Decimal("0.0002")


@pytest.mark.parametrize(
    "brut",
    [
        "```json {PROFIL} ```",  # clôture sur une seule ligne
        "```json\n{PROFIL}\n```\nVoilà le profil demandé.",  # prose après
        "Voici le résultat : {PROFIL}",  # prose avant
    ],
)
async def test_nettoyage_des_formes_enrobees(brut: str) -> None:
    enrobe = brut.replace("{PROFIL}", json.dumps(PROFIL_VALIDE))
    profil, _, cout = await analyser_cv(texte="x", appeler=_appel(enrobe))
    assert profil["titre"] == "Comptable"
    assert cout.cout_usd == Decimal("0.0001")  # lu du premier coup, sans relance


async def _jamais_appele(messages: Any, **_: Any) -> tuple[str, CoutAppel]:
    raise AssertionError("un appel payant a été fait sur une entrée inutilisable")


@pytest.mark.parametrize("texte", [None, "", "   \n\t "])
async def test_refuse_avant_dappeler_sans_texte_ni_image(texte: str | None) -> None:
    with pytest.raises(ValueError):
        await analyser_cv(texte=texte, appeler=_jamais_appele)


async def test_refuse_avant_dappeler_une_image_sans_type() -> None:
    with pytest.raises(ValueError):
        await analyser_cv(image=b"\xff\xd8", appeler=_jamais_appele)


async def test_refuse_une_image_pour_un_modele_texte_seul() -> None:
    with pytest.raises(ValueError):
        await analyser_cv(
            image=b"\xff\xd8",
            type_image="jpeg",
            modele="deepseek-v4-pro",
            appeler=_jamais_appele,
        )


async def test_le_cout_dun_premier_appel_survit_a_une_panne_sur_le_second() -> None:
    """IMPORTANT I-3 : tentative 1 FACTURÉE mais illisible, puis tentative 2 qui
    lève — le montant déjà dépensé ne doit pas partir avec l'exception, sinon
    `usage_counters` ne voit jamais de l'argent réellement sorti (§9)."""
    from src.core.erreurs import AnalyseIndisponible

    essais: list[int] = []

    async def appeler(messages: Any, **_: Any) -> tuple[str, CoutAppel]:
        essais.append(1)
        if len(essais) == 1:
            return "ceci n'est pas du json", COUT
        raise AnalyseIndisponible

    with pytest.raises(AnalyseIndisponible) as leve:
        await analyser_cv(texte="x", appeler=appeler)

    assert len(essais) == 2
    assert leve.value.cout == COUT.cout_usd
    # Rien de la réponse (qui porte le CV) ne doit avoir servi de contexte.
    assert leve.value.__context__ is None


async def test_une_panne_sur_le_premier_appel_ne_fabrique_pas_de_cout() -> None:
    """Le symétrique : rien n'a été facturé, donc `cout` reste vide — sinon on
    imputerait à l'utilisateur une dépense qui n'a pas eu lieu."""
    from src.core.erreurs import AnalyseIndisponible

    async def appeler(messages: Any, **_: Any) -> tuple[str, CoutAppel]:
        raise AnalyseIndisponible

    with pytest.raises(AnalyseIndisponible) as leve:
        await analyser_cv(texte="x", appeler=appeler)

    assert leve.value.cout is None


async def test_le_cout_dun_appel_interrompu_ne_fuite_pas_le_cv() -> None:
    """Le journal de ce chemin ne porte qu'un montant et un nom de type : la
    réponse déjà reçue, elle, contient le CV."""
    from src.core.erreurs import AnalyseIndisponible

    secret = "Awa Diop, comptable chez Alpha SARL"
    essais: list[int] = []

    async def appeler(messages: Any, **_: Any) -> tuple[str, CoutAppel]:
        essais.append(1)
        if len(essais) == 1:
            return secret, COUT
        raise AnalyseIndisponible

    with capture_logs() as journal, pytest.raises(AnalyseIndisponible):
        await analyser_cv(texte=secret, appeler=appeler)

    rendu = repr(journal)
    assert "cv_appel_interrompu_apres_paiement" in rendu
    assert secret not in rendu
    assert "Alpha SARL" not in rendu


@pytest.mark.parametrize(
    ("champ", "valeur"),
    [
        ("formations", [{"etablissement": None, "diplome": "CAP Aide-Comptable", "annee": None}]),
        ("formations", [{"diplome": "BFEM"}]),
        ("experiences", [{"entreprise": None, "poste": "Commerçant indépendant"}]),
    ],
)
async def test_une_ecole_ou_une_entreprise_absente_ne_fait_pas_rejeter_le_cv(
    champ: str, valeur: object
) -> None:
    """Un CAP sans nom d'école, un commerçant sans employeur : le modèle met null
    au lieu d'inventer, comme le prompt l'exige. Constaté sur un vrai CV le
    2026-10-21 : tout le CV était rejeté, deux appels payés pour rien."""
    profil, _, _ = await analyser_cv(
        texte="x", appeler=_appel(json.dumps(dict(PROFIL_VALIDE, **{champ: valeur})))
    )
    assert profil[champ] == valeur


async def test_un_document_qui_nest_pas_un_cv_est_refuse_sans_relance() -> None:
    """Modèle vierge, proposition commerciale, lettre : refusés, et pas relancés
    — le modèle a lu le document, il n'y a rien à retenter. L'appel payé
    voyage avec l'erreur."""
    appels = 0

    async def appeler(messages: Any, **_: Any) -> tuple[str, CoutAppel]:
        nonlocal appels
        appels += 1
        return json.dumps(dict(PROFIL_VALIDE, est_un_cv=False)), COUT

    with pytest.raises(CvPasUnCv) as info:
        await analyser_cv(texte="x", appeler=appeler)
    assert appels == 1
    assert info.value.cout == Decimal("0.0001")


async def test_le_verdict_est_un_cv_nentre_pas_dans_le_profil() -> None:
    profil, _, _ = await analyser_cv(texte="x", appeler=_appel(json.dumps(PROFIL_VALIDE)))
    assert "est_un_cv" not in profil


@pytest.mark.parametrize("valeur", [None, "oui", 1])
async def test_un_verdict_est_un_cv_mal_forme_est_illisible(valeur: object) -> None:
    mauvais = dict(PROFIL_VALIDE, est_un_cv=valeur)
    with pytest.raises(CvIllisible):
        await analyser_cv(texte="x", appeler=_appel(json.dumps(mauvais)))


async def test_le_prompt_demande_le_verdict_et_autorise_lecole_absente() -> None:
    from src.llm.prompts import PROMPT_CV

    assert '"est_un_cv": boolean' in PROMPT_CV
    assert '"etablissement": string | null' in PROMPT_CV
    assert '"entreprise": string | null' in PROMPT_CV
