"""Nettoyage des offres et extraction de l'email de candidature (CLAUDE.md §7)."""

from __future__ import annotations

import re

# Un email dans du texte libre ou du HTML. La ponctuation finale est retirée
# après coup : « ...à rh@xyz.sn. » ne doit pas produire « rh@xyz.sn. ».
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Faux positifs fréquents : noms de fichiers retina (« logo@2x.png »), assets.
_EXTENSIONS_FICHIER = frozenset(
    {"png", "jpg", "jpeg", "gif", "webp", "svg", "css", "js", "ico", "woff", "woff2"}
)

# Boîtes qui ne lisent pas de candidatures (§7).
_LOCAUX_NON_HUMAINS = frozenset(
    {"webmaster", "noreply", "no-reply", "donotreply", "postmaster", "mailer-daemon", "abuse"}
)

# Domaines de premier niveau attendus dans les annonces sénégalaises et
# internationales. Sert à recoller les adresses collées à la phrase suivante,
# pas à valider un domaine : une adresse à deux labels n'est jamais touchée.
_TLD_CONNUS = frozenset(
    {
        "sn", "ml", "ci", "bf", "tg", "bj", "gn", "mr", "ma", "tn", "dz", "cm", "ga", "cd",
        "fr", "be", "ch", "uk", "es", "it", "de", "pt", "nl", "se", "no", "dk", "pl", "ru",
        "ca", "us", "za", "ng", "gh", "ke", "eg", "ae", "sa", "in", "cn", "jp", "br",
        "com", "org", "net", "info", "biz", "edu", "gov", "int", "mil", "pro", "name",
        "io", "co", "me", "tv", "cc", "app", "dev", "africa", "ong", "ngo", "agency",
        "email", "group", "company", "solutions", "consulting", "jobs", "career", "careers",
    }
)

# Indices qu'une adresse est bien celle du recrutement, à préférer si plusieurs.
_INDICES_RECRUTEMENT = ("recrut", "rh", "job", "emploi", "career", "candidat", "hr")


def _recoller_domaine(domaine: str) -> str:
    """Retire les labels qu'une phrase collée à l'adresse a fait avaler.

    « ...à rh@xyz.sn.Merci de préciser » donne `xyz.sn.merci` : le domaine
    s'arrête en réalité au dernier label qui est un TLD connu. On ne touche
    jamais un domaine à deux labels — il n'y a rien à trancher.
    """
    labels = domaine.split(".")
    if len(labels) < 3 or labels[-1] in _TLD_CONNUS:
        return domaine
    for i in range(len(labels) - 2, 0, -1):
        if labels[i] in _TLD_CONNUS:
            return ".".join(labels[: i + 1])
    return domaine


def extract_apply_email(texte: str, domaine_source: str) -> str | None:
    """Retourne l'email de candidature d'une annonce, ou None.

    `domaine_source` est le domaine du portail d'où vient l'offre : ses propres
    adresses sont écartées, ce sont celles du site, pas celles du recruteur.
    """
    domaine_source = domaine_source.lower().removeprefix("www.")
    candidats: list[str] = []

    for brut in _EMAIL.findall(texte):
        adresse = brut.lower().rstrip(".,;:)")
        local, _, domaine = adresse.partition("@")
        domaine = _recoller_domaine(domaine)
        adresse = f"{local}@{domaine}"
        if domaine.rsplit(".", 1)[-1] in _EXTENSIONS_FICHIER:
            continue
        if local in _LOCAUX_NON_HUMAINS:
            continue
        if domaine == domaine_source or domaine.endswith("." + domaine_source):
            continue
        if adresse not in candidats:
            candidats.append(adresse)

    if not candidats:
        return None
    for adresse in candidats:
        if any(indice in adresse.partition("@")[0] for indice in _INDICES_RECRUTEMENT):
            return adresse
    return candidats[0]
