"""Socle commun aux scrapers (CLAUDE.md §7)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

import httpx


@dataclass(frozen=True, slots=True)
class RawJob:
    """Offre telle que lue sur une page de liste, avant enrichissement."""

    source: str
    source_id: str
    url: str
    title: str
    company: str | None = None
    location: str | None = None
    contract_type: str | None = None
    raw: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class JobDetail:
    """Champs obtenus en ouvrant la page de l'annonce."""

    description: str
    posted_at: datetime | None = None
    apply_email: str | None = None
    apply_method: str = "form"


@dataclass(frozen=True, slots=True)
class ResultatListe:
    """Offres lues sur une page, et nombre d'entrées écartées."""

    offres: tuple[RawJob, ...]
    ignorees: int


class StructureInattendueError(RuntimeError):
    """Le site ne rend plus la structure attendue (CLAUDE.md §7)."""


def verifier_coherence_liste(
    *, offres_lues: int, offres_ignorees: int, pages_annoncees: int
) -> None:
    """Vérifie qu'une page de liste ressemble encore à ce qu'on sait lire.

    Appelée à chaque passe sur les données réelles : c'est le seul garde-fou
    qui voit une refonte du site, les fixtures étant figées par construction.
    """
    if pages_annoncees <= 0:
        # Recherche légitimement vide : ce n'est pas une casse.
        return
    if offres_lues == 0:
        raise StructureInattendueError(
            f"{pages_annoncees} page(s) annoncée(s) mais aucune offre lue — "
            "les sélecteurs ne correspondent plus au site"
        )
    total = offres_lues + offres_ignorees
    if offres_ignorees * 2 > total:
        raise StructureInattendueError(
            f"{offres_ignorees}/{total} entrées écartées — structure partiellement changée"
        )


class CheminInterditError(RuntimeError):
    """Chemin exclu par le robots.txt du site visé (CLAUDE.md §2, interdiction n°4)."""


class PoliteClient:
    """Client HTTP qui tient les engagements de §2, interdiction n°4.

    User-Agent identifiable, un seul appel par domaine tous les `delai`
    secondes, et refus net des chemins exclus par le `robots.txt` du site.
    L'horloge et le sommeil sont injectés pour que les tests n'attendent pas.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        user_agent: str,
        delai: float,
        horloge: Callable[[], float],
        dormir: Callable[[float], Awaitable[None]],
        chemins_interdits: tuple[str, ...] = (),
    ) -> None:
        self._client = client
        self._user_agent = user_agent
        self._delai = delai
        self._horloge = horloge
        self._dormir = dormir
        self._chemins_interdits = tuple(c.lower() for c in chemins_interdits)
        self._dernier_appel: dict[str, float] = {}

    def _verifier_chemin(self, url: str) -> None:
        chemin = urlsplit(url).path.lower()
        if any(chemin.startswith(interdit) for interdit in self._chemins_interdits):
            raise CheminInterditError(f"chemin exclu par robots.txt : {url}")

    async def _attendre_son_tour(self, url: str) -> None:
        domaine = urlsplit(url).netloc
        precedent = self._dernier_appel.get(domaine)
        if precedent is not None:
            reste = self._delai - (self._horloge() - precedent)
            if reste > 0:
                await self._dormir(reste)
        self._dernier_appel[domaine] = self._horloge()

    async def _requete(self, methode: str, url: str, **kwargs: Any) -> httpx.Response:
        self._verifier_chemin(url)
        await self._attendre_son_tour(url)
        return await self._client.request(
            methode, url, headers={"User-Agent": self._user_agent}, **kwargs
        )

    async def get(self, url: str) -> httpx.Response:
        return await self._requete("GET", url)

    async def post(self, url: str, data: dict[str, Any]) -> httpx.Response:
        return await self._requete("POST", url, data=data)

    async def aclose(self) -> None:
        await self._client.aclose()
