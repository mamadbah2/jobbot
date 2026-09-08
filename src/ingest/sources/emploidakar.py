"""Scraper emploidakar.com — source prioritaire n°1 (CLAUDE.md §7).

Les offres ne sont pas dans le HTML de la page de liste : WP Job Manager les
sert via `POST /wp-admin/admin-ajax.php` (`action=job_manager_get_listings`),
chemin explicitement autorisé par le `robots.txt` du site. L'API REST
WordPress, elle, tombe sous challenge Cloudflare — ne pas l'utiliser (§7).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from selectolax.parser import HTMLParser, Node

from src.ingest.base import (
    BaseScraper,
    JobDetail,
    PageListe,
    RawJob,
    ResultatListe,
    StructureInattendueError,
)
from src.ingest.normalize import extract_apply_email

SOURCE = "emploidakar"
DOMAINE = "emploidakar.com"

# Seul point d'entrée autorisé par le robots.txt et non protégé par Cloudflare (§7).
URL_AJAX = "https://www.emploidakar.com/wp-admin/admin-ajax.php"
URL_ROBOTS = "https://www.emploidakar.com/robots.txt"

# Taille de page servie par le thème ; la changer ferait diverger `max_num_pages`.
OFFRES_PAR_PAGE = 17

# Zones exclues par le robots.txt du site : CVthèque et candidatures déposées
# par des tiers (§7). Codées en dur pour tenir même si robots.txt est injoignable.
CHEMINS_INTERDITS = ("/resume/", "/cv/", "/wp-content/uploads/job_applications/")

# WP Job Manager préfixe chaque <li> par la classe « post-<id> ».
_ID_OFFRE = re.compile(r"\bpost-(\d+)\b")


def _texte(noeud: Node | None) -> str | None:
    if noeud is None:
        return None
    valeur = noeud.text(separator=" ", strip=True)
    return valeur or None


def parse_list(payload: dict[str, Any]) -> ResultatListe:
    """Convertit la réponse AJAX en offres brutes.

    Les entrées inexploitables sont écartées mais **comptées** : un site qui
    change à moitié de structure doit se voir, pas se perdre en silence (§7).
    """
    html = payload.get("html") or ""
    if not html:
        return ResultatListe(offres=(), ignorees=0)

    offres: list[RawJob] = []
    ignorees = 0
    for item in HTMLParser(html).css("li.job_listing"):
        identifiant = _ID_OFFRE.search(item.attributes.get("class") or "")
        lien = item.css_first("a[href]")
        titre = _texte(item.css_first("h3"))
        if identifiant is None or lien is None or titre is None:
            # Écartée plutôt que de polluer la base, mais comptée : c'est
            # `verifier_coherence_liste` qui décide si le taux est anormal.
            ignorees += 1
            continue
        offres.append(
            RawJob(
                source=SOURCE,
                source_id=identifiant.group(1),
                url=(lien.attributes.get("href") or "").strip(),
                title=titre,
                company=_texte(item.css_first("div.company strong")),
                location=_texte(item.css_first("div.location")),
                contract_type=_texte(item.css_first("li.job-type")),
            )
        )
    return ResultatListe(offres=tuple(offres), ignorees=ignorees)


def nombre_de_pages(payload: dict[str, Any]) -> int:
    """Nombre total de pages annoncé par WP Job Manager."""
    return int(payload.get("max_num_pages") or 0)


def parse_detail(html: str) -> JobDetail:
    """Extrait description, date de publication et email de candidature."""
    arbre = HTMLParser(html)
    description = _texte(arbre.css_first("div.job_description")) or ""

    publiee_le: datetime | None = None
    balise_date = arbre.css_first("time[datetime]")
    if balise_date is not None:
        brut = (balise_date.attributes.get("datetime") or "").strip()
        try:
            publiee_le = datetime.fromisoformat(brut).replace(tzinfo=UTC)
        except ValueError:
            publiee_le = None

    mailto, lien_externe = _methode_declaree(arbre)
    email = mailto or extract_apply_email(description, DOMAINE)

    if email:
        # Un email explicite prime : y écrire est exactement ce que le recruteur
        # demande, et c'est la seule voie où l'auto-submit apporte sa valeur.
        methode = "email"
    elif lien_externe:
        # Site tiers, souvent à login : mode brouillon obligatoire (§2.1).
        methode = "external"
    else:
        methode = "form"

    return JobDetail(
        description=description,
        posted_at=publiee_le,
        apply_email=email,
        apply_method=methode,
        apply_url=lien_externe,
    )


def _methode_declaree(arbre: HTMLParser) -> tuple[str | None, str | None]:
    """Lit `div.application_details` : (email de candidature, lien externe).

    Ce bloc porte la consigne du recruteur et vit hors de la description.
    Un lien vers le portail lui-même n'est pas une candidature externe.
    """
    bloc = arbre.css_first("div.application_details")
    if bloc is None:
        return None, None

    mailto: str | None = None
    lien_externe: str | None = None
    for ancre in bloc.css("a[href]"):
        href = (ancre.attributes.get("href") or "").strip()
        if href.lower().startswith("mailto:"):
            adresse = href[len("mailto:") :].split("?", 1)[0]
            # Repasse par les rejets de §7 (boîtes non humaines, domaine du portail).
            mailto = mailto or extract_apply_email(adresse, DOMAINE)
        elif href.lower().startswith(("http://", "https://")):
            hote = urlsplit(href).netloc.lower().removeprefix("www.")
            if hote != DOMAINE and lien_externe is None:
                lien_externe = href
    return mailto, lien_externe


class EmploiDakarScraper(BaseScraper):
    """Source prioritaire n°1 (CLAUDE.md §7).

    La boucle — pagination, cohérence, robots.txt, arrêt sur challenge — est
    dans `BaseScraper` : il ne reste ici que les deux accès réseau.
    """

    source = SOURCE
    domaine = DOMAINE
    url_robots = URL_ROBOTS
    chemins_interdits = CHEMINS_INTERDITS

    async def fetch_list(self, page: int) -> PageListe:
        """Une page de liste, servie par WP Job Manager en AJAX (§7)."""
        reponse = await self._client.post(
            URL_AJAX,
            data={
                "action": "job_manager_get_listings",
                "page": str(page),
                "per_page": str(OFFRES_PAR_PAGE),
                "orderby": "date",
                "order": "DESC",
            },
        )
        reponse.raise_for_status()
        try:
            payload: dict[str, Any] = reponse.json()
        except ValueError as exc:
            # 200 mais pas du JSON : le point d'entrée a changé, il faut le revoir (§7).
            raise StructureInattendueError(
                "admin-ajax.php ne renvoie plus de JSON — point d'entrée à revérifier"
            ) from exc
        return PageListe(resultat=parse_list(payload), pages_totales=nombre_de_pages(payload))

    async def parse_detail(self, offre: RawJob) -> JobDetail:
        """Ouvre l'annonce pour la description et l'email de candidature (§7)."""
        reponse = await self._client.get(offre.url)
        reponse.raise_for_status()
        return parse_detail(reponse.text)
