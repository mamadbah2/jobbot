"""Socle commun aux scrapers (CLAUDE.md §7)."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar
from urllib.parse import urlsplit

import httpx

from src.ingest.robots import ReglesRobots
from src.logging_setup import get_logger

log = get_logger(__name__)


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
    # URL de candidature sur un site tiers, conservée pour le mode brouillon (§2.1).
    apply_url: str | None = None


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


def scraper_semble_casse(*, offres_vues: int, offres_connues: int) -> bool:
    """Vrai si la passe ne ramène plus rien alors que la source produisait (§7).

    « 0 offre alors qu'il en renvoyait > 0 la veille » : la veille est
    approximée par les offres déjà en base pour cette source. C'est le seul
    historique disponible sans table supplémentaire, et il suffit — une base
    peuplée prouve que le scraper a déjà fonctionné.

    Le compteur est le nombre d'offres **vues** sur les pages de liste, pas
    les nouvelles : la pagination incrémentale ramène légitimement 0 nouveauté
    quand le site n'a rien publié depuis la passe précédente.
    """
    return offres_vues == 0 and offres_connues > 0


class SourceBloqueeError(RuntimeError):
    """Le site a opposé un challenge anti-bot (CLAUDE.md §2 interdiction n°4)."""


# Un « // » en tête de chemin n'est pas replié par httpx et contournerait
# une liste noire écrite avec un seul slash.
_NORMALISER_SLASHS = re.compile(r"/{2,}")

# Statuts sous lesquels Cloudflare sert son interstitiel.
_STATUTS_SUSPECTS = frozenset({403, 429, 503})

# Marqueurs du challenge dans le corps de la réponse.
_MARQUEURS_CHALLENGE = (
    "just a moment",
    "cf-challenge",
    "__cf_chl",
    "cf_chl_opt",
    "cf-browser-verification",
)


def _est_un_challenge(reponse: httpx.Response) -> bool:
    """Reconnaît un interstitiel anti-bot, à distinguer d'un simple 403."""
    if reponse.headers.get("cf-mitigated"):
        return True
    if reponse.status_code not in _STATUTS_SUSPECTS:
        return False
    corps = reponse.text[:4096].lower()
    return any(marqueur in corps for marqueur in _MARQUEURS_CHALLENGE)


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
        regles: ReglesRobots | None = None,
        hotes_autorises: frozenset[str] = frozenset(),
    ) -> None:
        if client.follow_redirects:
            # Une redirection est décidée par un en-tête du site : elle échappe
            # au contrôle de chemin, à robots.txt et au délai de §2.4, qui ne
            # s'appliquent qu'avant l'appel. Refus structurel.
            raise ValueError(
                "PoliteClient refuse un client qui suit les redirection(s) : "
                "les sauts échappent aux garde-fous de §2.4"
            )
        self._client = client
        self._user_agent = user_agent
        self._delai = delai
        self._horloge = horloge
        self._dormir = dormir
        self._chemins_interdits = tuple(c.lower() for c in chemins_interdits)
        self._regles = regles
        self._hotes_autorises = frozenset(h.lower().removeprefix("www.") for h in hotes_autorises)
        self._dernier_appel: dict[str, float] = {}

    @property
    def delai(self) -> float:
        """Délai appliqué entre deux requêtes d'un même domaine (§2.4)."""
        return self._delai

    @property
    def user_agent(self) -> str:
        """Agent annoncé au site : c'est pour lui que robots.txt est interprété."""
        return self._user_agent

    def appliquer_regles(self, regles: ReglesRobots | None) -> None:
        """Installe les règles lues à l'exécution (robots.txt de la passe en cours)."""
        self._regles = regles

    def _verifier_chemin(self, url: str) -> None:
        # On contrôle le chemin RÉELLEMENT émis : httpx résout « .. », « . » et
        # l'encodage pourcent après nous. Contrôler l'URL brute laissait passer
        # « /offre-demploi/x/../../resume/quelquun ».
        cible = httpx.URL(url)
        hote = cible.host.lower().removeprefix("www.")
        if self._hotes_autorises and hote not in self._hotes_autorises:
            raise CheminInterditError(f"hôte hors périmètre de la source : {url}")

        chemin = _NORMALISER_SLASHS.sub("/", cible.path).lower()
        # Sans cette exception, on ne pourrait jamais relire robots.txt lui-même.
        if chemin == "/robots.txt":
            return
        # Plancher en dur : tient même si robots.txt est injoignable.
        if any(chemin.startswith(interdit) for interdit in self._chemins_interdits):
            raise CheminInterditError(f"chemin exclu par la liste noire : {url}")
        # Règles lues à l'exécution : elles voient les Disallow ajoutés depuis.
        if self._regles is not None and not self._regles.autorise(url):
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
        reponse = await self._client.request(
            methode, url, headers={"User-Agent": self._user_agent}, **kwargs
        )
        if _est_un_challenge(reponse):
            # On ne retente pas et on ne contourne pas (§2.4) : insister mène au
            # bannissement de l'IP du VPS, qui emporterait toutes les sources.
            raise SourceBloqueeError(
                f"challenge anti-bot sur {urlsplit(url).netloc} "
                f"(HTTP {reponse.status_code}) — source arrêtée, admin à prévenir"
            )
        return reponse

    async def get(self, url: str) -> httpx.Response:
        return await self._requete("GET", url)

    async def post(self, url: str, data: dict[str, Any]) -> httpx.Response:
        return await self._requete("POST", url, data=data)

    async def aclose(self) -> None:
        await self._client.aclose()


# --- Socle des scrapers (CLAUDE.md §7) --------------------------------------


@dataclass(frozen=True, slots=True)
class PageListe:
    """Une page de liste : ce qui a été lu, et le nombre de pages annoncé."""

    resultat: ResultatListe
    pages_totales: int


@dataclass(frozen=True, slots=True)
class OffreComplete:
    """Offre prête pour la base : entrée de liste + page de détail."""

    brut: RawJob
    detail: JobDetail


@dataclass(frozen=True, slots=True)
class ResultatPasse:
    """Bilan d'une passe d'ingestion sur une source."""

    offres: tuple[OffreComplete, ...]
    # Offres lues sur les pages de liste, connues ou non : c'est ce compteur,
    # et non le nombre de nouveautés, qui dit si le scraper fonctionne (§7).
    offres_vues: int
    ignorees: int
    pages_parcourues: int
    bloquee: bool


class BaseScraper(ABC):
    """Socle commun aux sources (CLAUDE.md §7).

    Une source implémente seulement `fetch_list()` et `parse_detail()` ; la
    boucle — pagination incrémentale, contrôle de cohérence à chaque page,
    lecture du `robots.txt`, arrêt propre sur challenge anti-bot — est ici,
    pour qu'aucune source ne puisse l'oublier ou la réécrire de travers.
    """

    #: Nom de la source, tel que stocké dans `jobs.source` (§5).
    source: ClassVar[str]
    #: Domaine visité, sans `www.` — sert au rejet des emails du portail (§7).
    domaine: ClassVar[str]
    #: URL du `robots.txt`, relu à chaque passe (§2.4).
    url_robots: ClassVar[str]
    #: Plancher en dur, appliqué même si `robots.txt` est injoignable (§7).
    chemins_interdits: ClassVar[tuple[str, ...]] = ()
    #: Délai minimal propre à la source, quand la reconnaissance en a validé un
    #: plus élevé que le réglage global (§7). 0 = on garde le réglage global.
    delai_minimum: ClassVar[float] = 0.0
    #: Garde-fou : une pagination folle ne doit pas marteler le site (§2.4).
    pages_max: ClassVar[int] = 50

    def __init__(self, client: PoliteClient) -> None:
        self._client = client

    @abstractmethod
    async def fetch_list(self, page: int) -> PageListe:
        """Récupère et parse une page de liste."""

    @abstractmethod
    async def parse_detail(self, offre: RawJob) -> JobDetail:
        """Ouvre la page d'une annonce et en extrait les champs manquants."""

    async def charger_robots(self) -> None:
        """Relit le `robots.txt` du site et l'applique au client (§2.4).

        Injoignable ou illisible → on continue sans, mais la liste noire en
        dur de la source reste un plancher : les zones sensibles de §7
        (CVthèque, candidatures de tiers) ne sont jamais ouvertes.
        """
        try:
            reponse = await self._client.get(self.url_robots)
        except httpx.HTTPError as exc:
            log.warning("robots_injoignable", source=self.source, erreur=str(exc))
            return
        if reponse.status_code != 200:
            log.warning("robots_indisponible", source=self.source, statut=reponse.status_code)
            return
        self._client.appliquer_regles(ReglesRobots.analyser(reponse.text, self._client.user_agent))

    async def collecter(self, ids_connus: AbstractSet[str]) -> ResultatPasse:
        """Passe complète : pages de liste, puis détail des seules nouveautés."""
        # Import local : `pagination` importe `RawJob` d'ici, un import en tête
        # de module créerait un cycle.
        from src.ingest.pagination import analyser_page

        nouvelles: list[RawJob] = []
        deja_vus: set[str] = set(ids_connus)
        offres_vues = 0
        ignorees = 0
        pages_parcourues = 0
        bloquee = False

        try:
            await self.charger_robots()
            page = 1
            pages_totales = 1  # borne provisoire, corrigée par la première réponse
            while page <= min(pages_totales, self.pages_max):
                liste = await self.fetch_list(page)
                pages_totales = liste.pages_totales
                verifier_coherence_liste(
                    offres_lues=len(liste.resultat.offres),
                    offres_ignorees=liste.resultat.ignorees,
                    pages_annoncees=pages_totales,
                )
                pages_parcourues += 1
                offres_vues += len(liste.resultat.offres)
                ignorees += liste.resultat.ignorees

                decision = analyser_page(liste.resultat.offres, deja_vus)
                nouvelles.extend(decision.nouvelles)
                deja_vus.update(offre.source_id for offre in decision.nouvelles)
                if not decision.continuer:
                    break
                page += 1
        except SourceBloqueeError as exc:
            # §2.4 : on ne retente pas et on ne contourne pas. Ce qui est déjà
            # lu est conservé, l'admin est prévenu par l'appelant.
            log.error("source_bloquee", source=self.source, erreur=str(exc))
            bloquee = True

        offres, bloquee_detail = await self._collecter_details(nouvelles)
        return ResultatPasse(
            offres=offres,
            offres_vues=offres_vues,
            ignorees=ignorees,
            pages_parcourues=pages_parcourues,
            bloquee=bloquee or bloquee_detail,
        )

    async def _collecter_details(
        self, nouvelles: list[RawJob]
    ) -> tuple[tuple[OffreComplete, ...], bool]:
        """Ouvre les pages de détail. Une annonce illisible ne perd pas la passe."""
        completes: list[OffreComplete] = []
        for offre in nouvelles:
            try:
                detail = await self.parse_detail(offre)
            except SourceBloqueeError as exc:
                log.error("source_bloquee", source=self.source, erreur=str(exc))
                return tuple(completes), True
            except (httpx.HTTPError, CheminInterditError) as exc:
                log.warning(
                    "detail_illisible",
                    source=self.source,
                    source_id=offre.source_id,
                    erreur=str(exc),
                )
                continue
            completes.append(OffreComplete(brut=offre, detail=detail))
        return tuple(completes), False
