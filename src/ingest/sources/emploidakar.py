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

from selectolax.parser import HTMLParser, Node

from src.ingest.base import JobDetail, RawJob
from src.ingest.normalize import extract_apply_email

SOURCE = "emploidakar"
DOMAINE = "emploidakar.com"

# WP Job Manager préfixe chaque <li> par la classe « post-<id> ».
_ID_OFFRE = re.compile(r"\bpost-(\d+)\b")


def _texte(noeud: Node | None) -> str | None:
    if noeud is None:
        return None
    valeur = noeud.text(separator=" ", strip=True)
    return valeur or None


def parse_list(payload: dict[str, Any]) -> list[RawJob]:
    """Convertit la réponse AJAX en offres brutes."""
    html = payload.get("html") or ""
    if not html:
        return []

    offres: list[RawJob] = []
    for item in HTMLParser(html).css("li.job_listing"):
        identifiant = _ID_OFFRE.search(item.attributes.get("class") or "")
        lien = item.css_first("a[href]")
        titre = _texte(item.css_first("h3"))
        if identifiant is None or lien is None or titre is None:
            # Une offre incomplète est ignorée plutôt que de polluer la base ;
            # le détecteur de scraper cassé (§7) verra la chute de volume.
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
    return offres


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

    email = extract_apply_email(description, DOMAINE)
    return JobDetail(
        description=description,
        posted_at=publiee_le,
        apply_email=email,
        apply_method="email" if email else "form",
    )
