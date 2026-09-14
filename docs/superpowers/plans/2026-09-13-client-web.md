# Client web — plan d'implémentation

> **Pour les agents :** SOUS-SKILL REQUISE : utiliser `superpowers:subagent-driven-development`
> (recommandé) ou `superpowers:executing-plans` pour dérouler ce plan tâche par tâche. Les étapes
> sont en cases à cocher (`- [ ]`).

**But :** écrire le client web Next.js qui ferme la Phase 2, plus l'endpoint `GET /offres` et le
branchement de l'ingestion à la demande dont il a besoin.

**Architecture :** Next.js sert les écrans en Server Components, **sans aucun composant client**.
Les formulaires sont des `<form>` HTML dont l'`action` est une Server Action : Next les soumet
même si le JavaScript n'arrive jamais. Les Server Actions appellent l'API FastAPI en interne sur
le réseau Compose ; le navigateur ne parle jamais à l'API directement.

**Stack :** Next 16.3.5, React 19.3.0, TypeScript, Node 24. Côté Python : FastAPI, SQLAlchemy 2.0
async, pytest.

**Spec :** `docs/superpowers/specs/2026-09-13-client-web-design.md` — la lire en entier avant de
commencer. Ce plan argumente depuis elle.

## Contraintes globales

Elles s'appliquent à **toutes** les tâches, sans être répétées dans chacune.

- **Aucune dépendance npm ou Python hors de celles listées ici.** Le CLAUDE.md §3 exige une
  justification écrite dans la PR pour chaque ajout. Ce plan n'ajoute que `next`, `react`,
  `react-dom`, `typescript` et `@types/*` — déjà justifiés au §3. **Pas de Tailwind, pas de
  librairie de composants, pas de Vitest, pas de Jest, pas de Playwright.**
- **Les tests web utilisent `node:test`**, le lanceur intégré à Node. Zéro dépendance.
- **Aucun texte utilisateur en clair dans un composant.** Tout dans `web/app/textes.ts`.
- **Vouvoiement**, français simple, aucun jargon RH. « améliorer votre CV », jamais « optimiser
  votre employabilité ».
- **Aucune adresse email dans un journal, une URL, ou un paramètre de requête.**
- **Plafond de 200 Ko transférés** sur `/connexion`. Critère de validation de phase.
- `mypy --strict` reste vert sur `src/` ; `tsc --noEmit` vert sur `web/`.
- **Ne jamais lancer `docker compose down -v` ni `alembic downgrade`.** La base de développement
  est partagée et porte 232 offres réelles.
- Commits en français, format `feat(portee): sujet`, terminés par les deux lignes d'attribution
  en vigueur dans le dépôt.

---

## Vue d'ensemble des fichiers

**Créés côté Python :**

| Fichier | Responsabilité |
|---|---|
| `src/api/schemas/offres.py` | Projection d'une offre vers le client — décide ce qui sort |
| `src/api/routers/offres.py` | `GET /offres` : lecture paginée + déclenchement du rafraîchissement |
| `tests/test_api_offres.py` | 401, tri, pagination, et absence de `description`/`raw` |
| `tests/test_textes_web.py` | Chaque code d'erreur Python a sa phrase dans `textes.ts` |

**Modifiés côté Python :** `src/api/app.py` (enregistrer le routeur), `src/worker_ingest.py`
(paramètre `planifier`), `tests/conftest.py` (fixture d'offres de test),
`tests/test_compose.py` (nouvelles assertions), `docker-compose.yml`, `.env.example`, `CLAUDE.md`.

**Créés côté web :**

| Fichier | Responsabilité |
|---|---|
| `web/package.json`, `web/tsconfig.json`, `web/next.config.ts` | Outillage |
| `web/app/layout.tsx` | Coquille HTML, langue, feuille de style |
| `web/app/styles.css` | Toute la présentation, écrite à la main |
| `web/app/api-contrat.ts` | Types et fonctions pures — aucun import de Next, donc testable |
| `web/app/api-client.ts` | **Le seul** module qui parle à l'API |
| `web/app/textes.ts` | Tous les textes utilisateur |
| `web/app/journal.ts` | Une ligne JSON par étape franchie |
| `web/app/page.tsx` | Redirection selon la session |
| `web/app/connexion/page.tsx` + `actions.ts` | Saisie de l'adresse |
| `web/app/connexion/code/page.tsx` + `actions.ts` | Saisie du code, et du nom si nouveau |
| `web/app/offres/page.tsx` | Liste des offres |
| `web/app/compte/page.tsx` + `actions.ts` | Compte et déconnexion |
| `web/test/api-contrat.test.ts` | Cookie, `X-Forwarded-For`, codes d'erreur |
| `web/mesure-poids.mjs` | Mesure du poids transféré, sortie en échec au-delà de 200 Ko |
| `web/Dockerfile` | Build multi-étapes, exécution `standalone` |

---

## Task 1 : `GET /offres` — schéma, routeur, tests

**Files:**
- Create: `src/api/schemas/offres.py`
- Create: `src/api/routers/offres.py`
- Create: `tests/test_api_offres.py`
- Modify: `src/api/app.py` (import et `include_router`)
- Modify: `tests/conftest.py` (ajouter la fixture `offres_test`)

**Interfaces:**
- Consomme : `deps.utilisateur_courant`, `deps.session_db` (existants), le modèle `Job`
  (`src/db/models.py:128`).
- Produit : `GET /offres?limite=&decalage=` → `PageOffres{offres: list[Offre], total: int}`.
  La tâche 7 en dépend pour l'écran `/offres`.

- [ ] **Step 1 : Ajouter la fixture d'offres de test dans `tests/conftest.py`**

À la fin du fichier. La base de développement porte **232 offres réelles** : cette fixture insère
ses propres lignes sous une source reconnaissable et ne purge **qu'elles**.

```python
SOURCE_TEST = "jobbot-test"


@pytest_asyncio.fixture
async def offres_test(
    base_utilisateurs_test: async_sessionmaker[AsyncSession],
) -> AsyncIterator[list[int]]:
    """Insère trois offres de test et ne purge qu'elles.

    La base de développement est partagée et porte 232 offres réelles (§3 du
    plan) : un `delete(Job)` sans filtre les détruirait.
    """
    from datetime import UTC, datetime

    from src.db.models import Job

    lignes = [
        Job(
            source=SOURCE_TEST,
            source_id="t1",
            url="https://exemple.test/1",
            title="Comptable",
            company="Alpha",
            location="Dakar",
            contract_type="CDI",
            description="x" * 5000,
            apply_method="email",
            apply_email="rh@alpha.test",
            posted_at=datetime(2026, 9, 10, tzinfo=UTC),
            fingerprint="fp-t1",
            raw={"secret": "ne doit pas sortir"},
        ),
        Job(
            source=SOURCE_TEST,
            source_id="t2",
            url="https://exemple.test/2",
            title="Developpeur",
            company="Beta",
            location="Thies",
            contract_type="CDD",
            description="y" * 5000,
            apply_method="form",
            posted_at=datetime(2026, 9, 12, tzinfo=UTC),
            fingerprint="fp-t2",
            raw={},
        ),
        Job(
            source=SOURCE_TEST,
            source_id="t3",
            url="https://exemple.test/3",
            title="Sans date",
            company="Gamma",
            location=None,
            contract_type=None,
            description=None,
            apply_method="external",
            posted_at=None,  # volontaire : teste le NULLS LAST
            fingerprint="fp-t3",
            raw=None,
        ),
    ]
    async with base_utilisateurs_test() as s:
        await s.execute(delete(Job).where(Job.source == SOURCE_TEST))
        s.add_all(lignes)
        await s.commit()
        ids = [ligne.id for ligne in lignes]
    yield ids
    async with base_utilisateurs_test() as s:
        await s.execute(delete(Job).where(Job.source == SOURCE_TEST))
        await s.commit()
```

- [ ] **Step 2 : Écrire les tests qui échouent — `tests/test_api_offres.py`**

```python
"""GET /offres (spec du client web §7).

Les offres ne sortent qu'à un compte connecté, et la projection est explicite :
`description` et `raw` ne doivent jamais traverser. La première pèse des
kilooctets par offre et la page a un budget de 200 Ko ; la seconde est la
charge brute du scraper.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import FournisseurCourrielEspion, demander_code_verification

ADRESSE = "offres@jobbot-test.sn"


def _connecter(client: TestClient, espion: FournisseurCourrielEspion) -> None:
    code = demander_code_verification(client, espion, ADRESSE)
    r = client.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "nom_complet": "Awa"},
    )
    assert r.status_code == 200


@pytest.mark.integration
def test_offres_sans_cookie_refuse(client_auth: TestClient) -> None:
    r = client_auth.get("/offres")
    assert r.status_code == 401
    assert r.json()["erreur"] == "jeton_invalide"


@pytest.mark.integration
def test_offres_listees_pour_un_compte_connecte(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    offres_test: list[int],
) -> None:
    _connecter(client_auth, fournisseur_courriel_espion)
    r = client_auth.get("/offres", params={"limite": 50})
    assert r.status_code == 200
    corps = r.json()
    titres = [o["titre"] for o in corps["offres"]]
    assert "Comptable" in titres
    assert corps["total"] >= 3


@pytest.mark.integration
def test_la_description_et_la_charge_brute_ne_sortent_jamais(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    offres_test: list[int],
) -> None:
    """Le test qui compte pour le budget de 200 Ko."""
    _connecter(client_auth, fournisseur_courriel_espion)
    r = client_auth.get("/offres", params={"limite": 50})
    for offre in r.json()["offres"]:
        assert "description" not in offre
        assert "raw" not in offre
        assert "fingerprint" not in offre
        assert "source_id" not in offre


@pytest.mark.integration
def test_les_offres_sans_date_ne_passent_pas_en_tete(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    offres_test: list[int],
) -> None:
    """Postgres place les NULL en tête sur un DESC : sans NULLS LAST, les
    offres sans date connue occuperaient la première page."""
    _connecter(client_auth, fournisseur_courriel_espion)
    nos_offres = [
        o
        for o in client_auth.get("/offres", params={"limite": 50}).json()["offres"]
        if o["id"] in offres_test
    ]
    assert [o["titre"] for o in nos_offres] == ["Developpeur", "Comptable", "Sans date"]


@pytest.mark.integration
def test_pagination(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    offres_test: list[int],
) -> None:
    _connecter(client_auth, fournisseur_courriel_espion)
    page1 = client_auth.get("/offres", params={"limite": 2, "decalage": 0}).json()
    page2 = client_auth.get("/offres", params={"limite": 2, "decalage": 2}).json()
    assert len(page1["offres"]) == 2
    ids1 = {o["id"] for o in page1["offres"]}
    ids2 = {o["id"] for o in page2["offres"]}
    assert not (ids1 & ids2), "deux pages successives ne doivent pas se recouvrir"


@pytest.mark.integration
def test_la_limite_est_plafonnee(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    _connecter(client_auth, fournisseur_courriel_espion)
    assert client_auth.get("/offres", params={"limite": 500}).status_code == 422
```

- [ ] **Step 3 : Lancer les tests, vérifier qu'ils échouent**

```bash
RUN_INTEGRATION_TESTS=1 pytest tests/test_api_offres.py -m integration -v
```

Attendu : **échec**, toutes les routes en 404 (`/offres` n'existe pas).

> ⚠️ **`-m integration` est obligatoire en plus de la variable.** `pyproject.toml` porte
> `addopts = "-m 'not integration'"` : sans le marqueur, pytest ne collecte rien et **sort en
> succès trompeur**. Postgres doit tourner sur `localhost:55432`.

- [ ] **Step 4 : Écrire `src/api/schemas/offres.py`**

```python
"""Ce qu'un client a le droit de savoir d'une offre.

Projection **explicite** et non un dump du modèle : `description` pèse des
kilooctets par offre alors que la page a un budget de 200 Ko transférés
(CLAUDE.md §11), et `raw` est la charge brute rendue par le scraper — elle n'a
aucune raison de traverser.

Champs en français, comme `schemas/auth.py` : c'est la convention du dépôt.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class Offre(BaseModel):
    id: int
    titre: str
    entreprise: str | None
    lieu: str | None
    type_contrat: str | None
    publiee_le: datetime | None
    url: str
    methode_candidature: str

    @classmethod
    def depuis(cls, job: Any) -> Offre:
        return cls(
            id=job.id,
            titre=job.title,
            entreprise=job.company,
            lieu=job.location,
            type_contrat=job.contract_type,
            publiee_le=job.posted_at,
            url=job.url,
            methode_candidature=job.apply_method,
        )


class PageOffres(BaseModel):
    offres: list[Offre]
    total: int
```

- [ ] **Step 5 : Écrire `src/api/routers/offres.py`** (sans le rafraîchissement — c'est la tâche 2)

```python
"""Liste des offres (spec du client web §7).

Réservée aux comptes connectés : une liste publique intégrale redistribuerait
gratuitement le fruit du scraping, et viderait de son intérêt le compte que le
modèle économique suppose (décision du 2026-09-13).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api import deps
from src.api.schemas.offres import Offre, PageOffres
from src.db.models import Job, User

router = APIRouter(tags=["offres"])


@router.get("/offres")
async def lister_offres(
    utilisateur: Annotated[User, Depends(deps.utilisateur_courant)],
    session: Annotated[AsyncSession, Depends(deps.session_db)],
    limite: Annotated[int, Query(ge=1, le=50)] = 20,
    decalage: Annotated[int, Query(ge=0)] = 0,
) -> PageOffres:
    """Pagination par décalage : à cette échelle un curseur serait de la
    complexité sans contrepartie, et `ix_jobs_posted_at` existe déjà.

    `nulls_last` n'est pas un détail : `jobs.posted_at` est nullable et Postgres
    place les NULL **en tête** sur un DESC. Sans lui, les offres sans date
    connue occuperaient la première page. Le second critère sur `id` rend
    l'ordre total — sans quoi deux pages successives peuvent répéter ou omettre
    une ligne.
    """
    requete = (
        select(Job)
        .order_by(nulls_last(Job.posted_at.desc()), Job.id.desc())
        .limit(limite)
        .offset(decalage)
    )
    lignes = (await session.execute(requete)).scalars().all()
    total = (await session.execute(select(func.count()).select_from(Job))).scalar_one()
    return PageOffres(offres=[Offre.depuis(j) for j in lignes], total=total)
```

- [ ] **Step 6 : Enregistrer le routeur dans `src/api/app.py`**

Ajouter `offres` à l'import des routeurs :

```python
from src.api.routers import auth, moi, offres, sante
```

puis, à la fin de `create_app()`, juste après `app.include_router(moi.router)` :

```python
    app.include_router(offres.router)
```

- [ ] **Step 7 : Lancer les tests, vérifier qu'ils passent**

```bash
RUN_INTEGRATION_TESTS=1 pytest tests/test_api_offres.py -m integration -v
pytest -q && mypy --strict src && ruff check src tests
```

Attendu : tout au vert.

- [ ] **Step 8 : Commit**

```bash
git add src/api/schemas/offres.py src/api/routers/offres.py src/api/app.py \
        tests/test_api_offres.py tests/conftest.py
git commit -m "feat(api): GET /offres, réservé aux comptes connectés"
```

---

## Task 2 : brancher le rafraîchissement à la demande sur `/offres`

`src/ingest/fraicheur.py` est écrit et testé depuis le 2026-09-08 et **rien ne l'appelle**. Il
attendait qu'un écran affiche les offres.

**Files:**
- Modify: `src/worker_ingest.py:184-213` (ajouter le paramètre `planifier`)
- Modify: `src/api/routers/offres.py` (déclencher en arrière-plan)
- Create: `tests/test_offres_rafraichissement.py`

**Interfaces:**
- Consomme : `rafraichir_a_la_demande(cache)` (`src/worker_ingest.py:184`),
  `deps.cache_redis`.
- Produit : rien de nouveau pour les autres tâches. `GET /offres` garde sa signature.

### Le piège à ne pas reproduire

`rafraichir_si_necessaire` planifie la passe par `asyncio.create_task` et **rend la main tout de
suite**. Or `deps.cache_redis` ferme son client Redis en fin de requête (`finally: await
client.aclose()`). Si on lui passe le client de la requête, la tâche de fond se retrouve avec une
connexion fermée : `liberer_verrou` échoue et **la source reste verrouillée pendant
`ingest_verrou_secondes`** (600 s par défaut). Panne silencieuse.

Deux précautions, toutes les deux nécessaires :

1. La tâche de fond **possède son propre client Redis** et ne le ferme qu'après que tout le
   travail planifié est terminé.
2. La référence à la tâche est **retenue dans un ensemble au niveau du module.** `asyncio` ne
   garde qu'une référence faible vers les tâches : sans cela le ramasse-miettes peut l'emporter
   en plein vol, au hasard.

- [ ] **Step 1 : Écrire le test qui échoue — `tests/test_offres_rafraichissement.py`**

```python
"""Le rafraîchissement déclenché par une visite ne doit pas survivre à la
fermeture du client Redis de la requête (spec du client web §7)."""

from __future__ import annotations

import asyncio

import pytest

from src.worker_ingest import rafraichir_a_la_demande
from tests.conftest import FauxCache


async def test_rafraichir_a_la_demande_accepte_un_planificateur() -> None:
    """Sans ce paramètre, l'API ne peut pas savoir quand la passe est finie,
    donc ne peut pas fermer son client Redis au bon moment."""
    cache = FauxCache()
    planifiees: list[asyncio.Future[None]] = []

    decisions = await rafraichir_a_la_demande(
        cache, planifier=lambda coro: planifiees.append(asyncio.ensure_future(coro))
    )

    assert decisions, "au moins une source doit être décidée"
    # On annule : ce test ne doit lancer aucun scraping réel.
    for tache in planifiees:
        tache.cancel()
    await asyncio.gather(*planifiees, return_exceptions=True)


async def test_une_seconde_visite_immediate_ne_relance_rien() -> None:
    """Le verrou et l'horodatage de dernière passe font leur travail."""
    cache = FauxCache()
    planifiees: list[asyncio.Future[None]] = []
    planifier = lambda coro: planifiees.append(asyncio.ensure_future(coro))  # noqa: E731

    await rafraichir_a_la_demande(cache, planifier=planifier)
    premier_lot = len(planifiees)
    await rafraichir_a_la_demande(cache, planifier=planifier)

    assert len(planifiees) == premier_lot, "la seconde visite ne doit rien replanifier"
    for tache in planifiees:
        tache.cancel()
    await asyncio.gather(*planifiees, return_exceptions=True)
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

```bash
pytest tests/test_offres_rafraichissement.py -v
```

Attendu : `TypeError: rafraichir_a_la_demande() got an unexpected keyword argument 'planifier'`.

- [ ] **Step 3 : Ajouter le paramètre `planifier` à `src/worker_ingest.py`**

Remplacer la signature ligne 184 et l'appel à `rafraichir_si_necessaire` :

```python
async def rafraichir_a_la_demande(
    cache: CacheRedis,
    *,
    planifier: Callable[[Coroutine[Any, Any, None]], Any] = asyncio.create_task,
) -> dict[str, Decision]:
    """Point d'entrée de l'API : appelé quand un utilisateur ouvre la plateforme.

    Ne bloque jamais l'appelant. L'API sert les offres déjà en base, et cette
    fonction déclenche au besoin une passe de fond — au plus une à la fois par
    source, grâce au verrou Redis (§2.4).

    `planifier` est injectable pour que l'appelant sache quand le travail de
    fond est terminé : l'API doit fermer son client Redis **après**, pas avant
    (spec du client web §7).
    """
```

et, dans la boucle, ajouter l'argument :

```python
        decisions[classe.source] = await rafraichir_si_necessaire(
            cache,
            classe.source,
            fraicheur_secondes=settings.ingest_fraicheur_minutes * 60,
            duree_verrou_secondes=settings.ingest_verrou_secondes,
            executer_passe=passe,
            planifier=planifier,
        )
```

Ajouter les imports manquants en tête de fichier s'ils n'y sont pas déjà :

```python
import asyncio
from collections.abc import Callable, Coroutine
from typing import Any
```

- [ ] **Step 4 : Lancer, vérifier que ça passe**

```bash
pytest tests/test_offres_rafraichissement.py -v
```

- [ ] **Step 5 : Déclencher depuis `src/api/routers/offres.py`**

Ajouter en tête du fichier :

```python
import asyncio

import redis.asyncio as aioredis

from src.config import get_settings
from src.logging_setup import get_logger
from src.worker_ingest import rafraichir_a_la_demande

log = get_logger(__name__)

# `asyncio` ne retient qu'une référence FAIBLE vers une tâche : sans cet
# ensemble, le ramasse-miettes peut emporter la passe en plein vol, au hasard.
_TACHES_DE_FOND: set[asyncio.Task[None]] = set()


async def _rafraichir_en_arriere_plan() -> None:
    """Possède son propre client Redis, et ne le ferme qu'à la toute fin.

    Le client de `deps.cache_redis` est fermé en fin de requête : le passer à
    une tâche de fond laisserait `liberer_verrou` échouer, et la source
    resterait verrouillée pendant `ingest_verrou_secondes` (spec §7).
    """
    client: aioredis.Redis = aioredis.from_url(
        get_settings().redis_url, decode_responses=True
    )
    planifiees: list[asyncio.Task[None]] = []
    try:
        await rafraichir_a_la_demande(
            client, planifier=lambda coro: planifiees.append(asyncio.create_task(coro))
        )
        if planifiees:
            await asyncio.gather(*planifiees, return_exceptions=True)
    except Exception as exc:  # noqa: BLE001 — une passe ratée ne casse jamais l'affichage
        log.error("rafraichissement_depuis_api_echoue", type_erreur=type(exc).__name__)
    finally:
        await client.aclose()
```

Puis, à la fin de `lister_offres`, **juste avant le `return`** :

```python
    tache = asyncio.create_task(_rafraichir_en_arriere_plan())
    _TACHES_DE_FOND.add(tache)
    tache.add_done_callback(_TACHES_DE_FOND.discard)
```

- [ ] **Step 6 : Vérifier que les tests d'offres passent toujours**

```bash
RUN_INTEGRATION_TESTS=1 pytest tests/test_api_offres.py -m integration -v
pytest -q && mypy --strict src && ruff check src tests
```

Attendu : vert. Le rafraîchissement ne doit pas ralentir la réponse — si un test d'offres devient
lent, c'est que `rafraichir_a_la_demande` est attendu au lieu d'être planifié.

- [ ] **Step 7 : Commit**

```bash
git add src/worker_ingest.py src/api/routers/offres.py tests/test_offres_rafraichissement.py
git commit -m "feat(api): brancher le rafraîchissement à la demande sur GET /offres"
```

---

## Task 3 : `docker-compose.yml`, `.env.example`, et le piège des plafonds par IP

**Files:**
- Modify: `docker-compose.yml` (service `api` et service `web`)
- Modify: `.env.example`
- Modify: `tests/test_compose.py`

**Interfaces:**
- Produit : les variables `API_BASE_URL`, `PROXY_IPS_DE_CONFIANCE`, `WEB_HOST_PORT`, consommées
  par les tâches 5 à 8.

### Pourquoi les trois pièces ne valent que prises ensemble

Les plafonds anti-abus de l'API sont indexés sur l'IP (`auth_envois_par_ip_heure`,
`auth_verifications_par_ip_heure`). Next relayant tous les appels, l'API verrait l'IP du conteneur
`web` pour **tous** les utilisateurs : les compteurs s'effondrent en un seul seau et les premiers
inscrits de l'heure bloquent tous les suivants, sans le moindre message d'erreur.

La parade a trois pièces : `X-Forwarded-For` émis par Next (tâche 5),
`PROXY_IPS_DE_CONFIANCE` renseigné (ici), et **l'API rabattue sur `127.0.0.1`** (ici).
**En poser deux sur trois rend l'usurpation d'IP plus facile qu'aujourd'hui** : déclarer un proxy
de confiance sans fermer l'accès direct à l'API, c'est autoriser n'importe qui à s'annoncer avec
l'IP de son choix.

- [ ] **Step 1 : Écrire les tests qui échouent — ajouts à `tests/test_compose.py`**

```python
def test_l_api_reste_sur_la_boucle_locale() -> None:
    """Si l'API est joignable de l'extérieur, on contourne Next et on se forge
    le X-Forwarded-For de son choix : les plafonds par IP ne valent plus rien
    (spec du client web §6)."""
    assert all(str(p).startswith("127.0.0.1:") for p in SERVICES["api"]["ports"])


def test_le_web_n_est_plus_derriere_un_profil() -> None:
    """Le service était déclaré en prévision ; il devient réel."""
    assert "profiles" not in SERVICES["web"]


def test_le_web_est_publie_sur_l_hote() -> None:
    assert any("WEB_HOST_PORT" in str(p) for p in SERVICES["web"]["ports"])


def test_le_web_attend_que_l_api_soit_saine() -> None:
    assert SERVICES["web"]["depends_on"]["api"] == {"condition": "service_healthy"}
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

```bash
pytest tests/test_compose.py -v
```

Attendu : les quatre nouveaux tests échouent, les anciens passent.

- [ ] **Step 3 : Modifier le service `api` dans `docker-compose.yml`**

Remplacer son bloc `ports` par :

```yaml
    # Rabattu sur la boucle locale le 2026-09-13, quand `web` est devenu le
    # frontal : le navigateur ne parle plus jamais à l'API directement. Laisser
    # 0.0.0.0 permettrait de contourner Next et de se forger le
    # `X-Forwarded-For` de son choix, ce qui annulerait les plafonds par IP de
    # `core/auth/limites.py`. Le parcours curl du README continue de
    # fonctionner en local. Même politique que postgres ci-dessus.
    ports:
      - "127.0.0.1:${HTTP_PORT:-8080}:${HTTP_PORT:-8080}"
```

- [ ] **Step 4 : Modifier le service `web`**

Remplacer le bloc `web` en entier :

```yaml
  # Client Next.js — le seul client du produit depuis le 2026-09-12, et le
  # seul frontal HTTP depuis le 2026-09-13.
  web:
    build:
      context: ./web
    environment:
      API_BASE_URL: "http://api:${HTTP_PORT:-8080}"
      COOKIE_SESSION_NOM: "${COOKIE_SESSION_NOM:-jobbot_session}"
      ENVIRONMENT: "${ENVIRONMENT:-dev}"
    ports:
      - "${WEB_HOST_PORT:-3000}:3000"
    depends_on:
      api:
        condition: service_healthy
    restart: unless-stopped
```

> `env_file: .env` est remplacé par un `environment` explicite : le conteneur web n'a aucune
> raison de recevoir `DEEPSEEK_API_KEY`, `POSTGRES_PASSWORD` ni `JWT_SECRET`. Un secret qui
> n'entre pas dans un processus ne peut pas en fuir.

- [ ] **Step 5 : Documenter les variables dans `.env.example`**

Ajouter une section, en reprenant le ton des commentaires existants :

```bash
# --- Client web ---
# Port de publication du client web sur l'hôte.
WEB_HOST_PORT=3000

# IP ou réseau du reverse proxy à qui l'API fait confiance pour l'en-tête
# X-Forwarded-For. Depuis le 2026-09-13, `web` est ce proxy : sans cette
# valeur, les plafonds par IP de l'authentification comptent TOUS les
# utilisateurs dans le même seau, et les premiers inscrits de l'heure
# bloquent tous les suivants.
# En Docker Compose, le réseau par défaut est en 172.16.0.0/12.
# NE JAMAIS mettre "*" : n'importe qui pourrait alors usurper son IP.
PROXY_IPS_DE_CONFIANCE=172.16.0.0/12
```

- [ ] **Step 6 : Lancer les tests, vérifier qu'ils passent**

```bash
pytest tests/test_compose.py -v && pytest -q
```

- [ ] **Step 7 : Vérifier que le fichier compose reste valide**

```bash
docker compose config >/dev/null && echo "compose OK"
```

- [ ] **Step 8 : Commit**

```bash
git add docker-compose.yml .env.example tests/test_compose.py
git commit -m "chore(compose): web devient le frontal, l'API se rabat sur la boucle locale"
```

---

## Task 4 : squelette Next et mesure du poids

Cette tâche produit une page qui s'affiche et un chiffre. **Aucune logique métier.** Le but est
d'avoir la mesure des 200 Ko avant d'écrire quoi que ce soit, pas après.

**Files:**
- Create: `web/package.json`, `web/tsconfig.json`, `web/next.config.ts`, `web/.gitignore`
- Create: `web/app/layout.tsx`, `web/app/styles.css`
- Create: `web/mesure-poids.mjs`

**Interfaces:**
- Produit : `npm run build`, `npm start`, `npm test`, `npm run typecheck`, `npm run mesure`.
  Les tâches 5 à 8 s'appuient dessus.

- [ ] **Step 1 : `web/package.json`**

```json
{
  "name": "jobbot-web",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "typecheck": "tsc --noEmit",
    "test": "node --test test/",
    "mesure": "node mesure-poids.mjs"
  },
  "dependencies": {
    "next": "16.3.5",
    "react": "19.3.0",
    "react-dom": "19.3.0"
  },
  "devDependencies": {
    "@types/node": "24.9.2",
    "@types/react": "19.2.7",
    "typescript": "5.9.3"
  }
}
```

> Node 24 exécute TypeScript nativement : c'est ce qui permet de tester sans Vitest ni Jest, donc
> sans dépendance à justifier au titre du §3. Les fichiers de test importent les modules avec leur
> extension `.ts` explicite — c'est requis par le dépouillement de types.
> **Vérifier d'abord** que la machine est bien en Node ≥ 22.18 (`node -v`). Si ce n'est pas le cas,
> **ne pas ajouter un lanceur de tests** pour contourner : le signaler au porteur du projet.

- [ ] **Step 2 : `web/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "ES2022"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 3 : `web/next.config.ts`**

```ts
import type { NextConfig } from 'next'

const config: NextConfig = {
  // L'image de production ne doit pas porter les node_modules de build.
  output: 'standalone',
  // Aucune image distante, aucun optimiseur : la cible est un Android
  // d'entrée de gamme sur data comptée (CLAUDE.md §11).
  images: { unoptimized: true },
  poweredByHeader: false,
}

export default config
```

- [ ] **Step 4 : `web/.gitignore`**

```
node_modules/
.next/
next-env.d.ts
```

- [ ] **Step 5 : `web/app/styles.css`**

Écrite à la main. **Police système : zéro octet transféré**, affichage immédiat, aucun saut de
mise en page. C'est une révision assumée du §11 du CLAUDE.md, décidée le 2026-09-13.

```css
:root {
  --encre: #1a1a1a;
  --papier: #ffffff;
  --trait: #d4d4d4;
  --accent: #0a6b4a;
  --alerte: #9b2226;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  padding: 1.25rem;
  max-width: 34rem;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  font-size: 1rem;
  line-height: 1.5;
  color: var(--encre);
  background: var(--papier);
}

h1 { font-size: 1.35rem; margin: 0 0 0.5rem; }
p { margin: 0 0 1rem; }

label { display: block; margin-bottom: 0.35rem; font-weight: 600; }

input {
  width: 100%;
  padding: 0.7rem;
  font-size: 1rem;
  border: 1px solid var(--trait);
  border-radius: 4px;
}

button {
  width: 100%;
  margin-top: 1rem;
  padding: 0.8rem;
  font-size: 1rem;
  color: var(--papier);
  background: var(--accent);
  border: 0;
  border-radius: 4px;
  cursor: pointer;
}

.erreur {
  padding: 0.7rem;
  margin-bottom: 1rem;
  color: var(--alerte);
  border: 1px solid var(--alerte);
  border-radius: 4px;
}

.offre { padding: 0.8rem 0; border-bottom: 1px solid var(--trait); }
.offre h2 { font-size: 1rem; margin: 0 0 0.2rem; }
.offre .meta { font-size: 0.875rem; color: #555; }

nav { margin-bottom: 1.5rem; font-size: 0.875rem; }
```

- [ ] **Step 6 : `web/app/layout.tsx`**

```tsx
import type { Metadata } from 'next'
import './styles.css'

export const metadata: Metadata = {
  title: 'JobBot',
  description: "Les offres d'emploi du Sénégal, réunies au même endroit.",
}

export default function RacineLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  )
}
```

- [ ] **Step 7 : `web/mesure-poids.mjs`**

```js
// Mesure le poids réellement transféré d'une page, compression comprise.
//
// Sans dépendance : ajouter Playwright pour ça coûterait plus que ça ne
// rapporte (CLAUDE.md §3).
//
// LIMITE ASSUMÉE : ne voit pas un fragment chargé dynamiquement. Avec zéro
// composant client et aucun import dynamique, il n'y en a pas. Si cela change,
// cette mesure devient fausse SANS PRÉVENIR — d'où la double vérification en
// vrai navigateur à la validation de la phase.

const BASE = process.env.URL_BASE ?? 'http://127.0.0.1:3000'
const CHEMIN = process.argv[2] ?? '/connexion'
const PLAFOND = Number(process.env.PLAFOND_OCTETS ?? 200 * 1024)

const ENTETES = { 'Accept-Encoding': 'gzip, deflate, br' }

async function poids(url) {
  const reponse = await fetch(url, { headers: ENTETES, redirect: 'follow' })
  if (!reponse.ok) throw new Error(`${url} → HTTP ${reponse.status}`)
  const corps = await reponse.arrayBuffer()
  return { octets: corps.byteLength, texte: reponse.headers.get('content-type') ?? '' }
}

const html = await fetch(`${BASE}${CHEMIN}`, { headers: ENTETES, redirect: 'follow' })
if (!html.ok) throw new Error(`${CHEMIN} → HTTP ${html.status}`)
const source = await html.text()
const octetsHtml = Buffer.byteLength(source)

const refs = new Set()
for (const m of source.matchAll(/<script[^>]+src="([^"]+)"/g)) refs.add(m[1])
for (const m of source.matchAll(/<link[^>]+href="([^"]+\.(?:css|js|woff2?))"/g)) refs.add(m[1])

let total = octetsHtml
const lignes = [['(document HTML)', octetsHtml]]
for (const ref of refs) {
  const url = ref.startsWith('http') ? ref : `${BASE}${ref}`
  const { octets } = await poids(url)
  total += octets
  lignes.push([ref, octets])
}

lignes.sort((a, b) => b[1] - a[1])
for (const [nom, octets] of lignes) {
  console.log(`${String(Math.round(octets / 1024)).padStart(5)} Ko  ${nom}`)
}
console.log('—'.repeat(50))
console.log(`${String(Math.round(total / 1024)).padStart(5)} Ko  TOTAL pour ${CHEMIN}`)
console.log(`${String(Math.round(PLAFOND / 1024)).padStart(5)} Ko  plafond`)

if (total > PLAFOND) {
  console.error(`\nÉCHEC : ${Math.round(total / 1024)} Ko dépassent le plafond.`)
  process.exit(1)
}
console.log('\nOK.')
```

- [ ] **Step 8 : Installer, construire et mesurer**

La page `/connexion` n'existe pas encore : mesurer la racine pour obtenir le **coût du framework
seul**, qui est le chiffre à connaître avant d'écrire les écrans. Créer temporairement
`web/app/page.tsx` :

```tsx
export default function Page() {
  return <h1>JobBot</h1>
}
```

puis :

```bash
cd web && npm install && npm run build && npm start &
sleep 5 && npm run mesure -- /
```

**Noter le total dans le message de commit.** C'est la part du budget de 200 Ko qui appartient au
framework et sur laquelle on n'a aucune prise. Si elle dépasse déjà 150 Ko, **s'arrêter et le
signaler au porteur du projet** : le design repose sur l'hypothèse d'environ 90 Ko.

- [ ] **Step 9 : Commit**

```bash
git add web/
git commit -m "feat(web): squelette Next, feuille de style, mesure du poids transféré"
```

---

## Task 5 : `api-contrat.ts`, `api-client.ts`, `textes.ts`, `journal.ts` et leurs tests

Le cœur du client. Aucune page ici.

**Files:**
- Create: `web/app/api-contrat.ts` — types et fonctions pures, **aucun import de Next**
- Create: `web/app/api-client.ts` — la couche réseau, qui elle importe `next/headers`
- Create: `web/app/textes.ts`, `web/app/journal.ts`
- Create: `web/test/api-contrat.test.ts`
- Create: `tests/test_textes_web.py`

### Pourquoi deux modules et pas un

`next/headers` ne peut être importé qu'à l'intérieur du runtime de Next : un test lancé par
`node --test` qui l'atteindrait, ne serait-ce qu'en haut d'un fichier importé, échouerait à
l'import. Les fonctions qui méritent un test unitaire — découpage du `X-Forwarded-For`, lecture
du `Set-Cookie`, attributs de cookie — n'ont besoin d'aucun contexte de requête. Elles vivent
donc dans `api-contrat.ts`, testable hors de Next, et `api-client.ts` s'appuie dessus.

**Interfaces:**
- Produit par `api-contrat.ts` :
  - `class ErreurApi extends Error { code: string; statut: number; reessayerDans?: number }`
  - `ipCliente(entetes: Headers): string | null`
  - `lireCookieSession(entetes: Headers, nom?: string): CookieSession | null`
  - `attributsCookieSession(maxAge: number)`, `attributsCookieAdresse()`, `COOKIE_ADRESSE`
  - les types `Utilisateur`, `Offre`, `PageOffres`, `CookieSession`
- Produit par `api-client.ts`, consommé par les tâches 6 et 7 :
  - `demanderCode(adresse: string): Promise<void>`
  - `verifierCode(adresse: string, code: string, nomComplet?: string): Promise<{utilisateur: Utilisateur, session: CookieSession | null}>`
  - `moi(): Promise<Utilisateur | null>` — `null` si pas de session valide
  - `listerOffres(limite?: number, decalage?: number): Promise<PageOffres>`
  - `deconnecter(): Promise<void>`
  - `type Utilisateur = { id: number; email: string; nom_complet: string | null; etat: string }`
  - `type CookieSession = { nom: string; valeur: string; maxAge: number }`
  - `texteErreur(code: string | undefined): string | null` depuis `textes.ts`
  - `journaliser(etape: string): void` depuis `journal.ts`

### La règle de l'IP unique

Next reçoit `X-Forwarded-For` du reverse proxy TLS et le retransmet à l'API. **On ne transmet
qu'une seule IP — la première de la chaîne reçue**, jamais la chaîne entière. Raison : les
implémentations de proxy ne s'accordent pas sur l'extrémité de la chaîne qui fait foi. Avec une
seule valeur, la première et la dernière sont la même, et la question ne se pose plus.

- [ ] **Step 1 : `web/app/textes.ts`**

```ts
// TOUS les textes destinés à l'utilisateur. Aucun texte en clair dans un
// composant — convention héritée de `src/bot/texts.py`, qui survit au bot.
//
// Vouvoiement partout, français simple, aucun jargon RH (CLAUDE.md §11).

export const ERREURS: Record<string, string> = {
  adresse_invalide: "Cette adresse email ne semble pas valide. Vérifiez-la et réessayez.",
  trop_de_demandes: "Vous avez fait trop d'essais. Patientez un moment avant de recommencer.",
  plafond_global_atteint:
    "Le service reçoit trop de demandes en ce moment. Réessayez dans quelques minutes.",
  envoi_impossible:
    "Nous n'arrivons pas à envoyer le code pour l'instant. Réessayez dans quelques minutes.",
  code_invalide: "Ce code n'est pas le bon. Vérifiez votre email et ressaisissez-le.",
  code_expire: "Ce code a expiré. Demandez-en un nouveau.",
  inscription_incomplete: "Il nous manque votre nom pour créer votre compte.",
  nom_invalide: "Ce nom ne semble pas valide. Utilisez votre prénom et votre nom.",
  jeton_invalide: "Votre session a expiré. Reconnectez-vous.",
  erreur_metier: "Une erreur est survenue. Réessayez.",
  defaut: "Une erreur est survenue. Réessayez.",
}

export function texteErreur(code: string | undefined): string | null {
  if (!code) return null
  return ERREURS[code] ?? ERREURS.defaut
}

export const T = {
  titreAdresse: 'Votre adresse email',
  aideAdresse: "Nous vous envoyons un code à 6 chiffres. Il n'y a pas de mot de passe.",
  champAdresse: 'Adresse email',
  boutonAdresse: 'Recevoir mon code',

  titreCode: 'Votre code',
  aideCode: 'Saisissez le code à 6 chiffres que vous venez de recevoir.',
  champCode: 'Code à 6 chiffres',
  champNom: 'Votre prénom et votre nom',
  aideNom: "C'est votre première connexion : indiquez-nous votre nom.",
  boutonCode: 'Continuer',

  titreOffres: "Offres d'emploi",
  aucuneOffre: "Aucune offre pour le moment. Revenez un peu plus tard.",
  voirOffre: "Voir l'offre",
  parEmail: 'Candidature par email',
  parFormulaire: 'Candidature sur le site',
  parSiteExterne: 'Candidature sur un autre site',

  titreCompte: 'Votre compte',
  boutonDeconnexion: 'Se déconnecter',
  lienOffres: 'Les offres',
  lienCompte: 'Mon compte',
}
```

- [ ] **Step 2 : `web/app/journal.ts`**

```ts
// Une ligne JSON par étape franchie (CLAUDE.md §11 : « compter et logger les
// abandons à chaque étape »).
//
// JAMAIS d'adresse email : le dépôt porte deux tests dont c'est l'objet
// (tests/test_logs_sans_pii.py). L'étape suffit à voir où le parcours perd
// des gens ; l'identité n'y ajoute rien et constituerait un fichier de
// données personnelles.

export function journaliser(etape: string, extra: Record<string, string | number> = {}): void {
  console.log(JSON.stringify({ evenement: 'parcours', etape, ...extra }))
}
```

- [ ] **Step 3 : `web/app/api-contrat.ts`** — types et fonctions pures, testable hors de Next

```ts
// Aucun import de Next ici : ce module doit être importable par `node --test`.
// Tout ce qui a besoin du contexte de requête vit dans api-client.ts.

export const NOM_COOKIE = process.env.COOKIE_SESSION_NOM ?? 'jobbot_session'
const EN_PROD = process.env.ENVIRONMENT === 'prod'

export type Utilisateur = {
  id: number
  email: string
  nom_complet: string | null
  etat: string
}

export type Offre = {
  id: number
  titre: string
  entreprise: string | null
  lieu: string | null
  type_contrat: string | null
  publiee_le: string | null
  url: string
  methode_candidature: string
}

export type PageOffres = { offres: Offre[]; total: number }

export type CookieSession = { nom: string; valeur: string; maxAge: number }

export class ErreurApi extends Error {
  constructor(
    readonly code: string,
    readonly statut: number,
    readonly reessayerDans?: number,
  ) {
    super(code)
    this.name = 'ErreurApi'
  }
}

/** Une SEULE IP, jamais la chaîne : les proxys ne s'accordent pas sur
 *  l'extrémité qui fait foi. Avec une seule valeur, la question disparaît. */
export function ipCliente(entetes: Headers): string | null {
  const chaine = entetes.get('x-forwarded-for')
  if (!chaine) return null
  const premiere = chaine.split(',')[0]?.trim()
  return premiere ? premiere : null
}

/** Extrait le cookie de session du `Set-Cookie` renvoyé par l'API. */
export function lireCookieSession(entetes: Headers, nom = NOM_COOKIE): CookieSession | null {
  for (const brut of entetes.getSetCookie()) {
    const [paire, ...attributs] = brut.split(';')
    const separateur = paire.indexOf('=')
    if (paire.slice(0, separateur).trim() !== nom) continue
    const maxAge = attributs
      .map((a) => a.trim().toLowerCase())
      .find((a) => a.startsWith('max-age='))
    return {
      nom,
      valeur: paire.slice(separateur + 1),
      maxAge: maxAge ? Number(maxAge.slice('max-age='.length)) : 0,
    }
  }
  return null
}

/** Attributs du cookie de session, posés par le client web.
 *  Ils doivent refléter ceux de l'API (`poser_cookie` dans routers/auth.py) :
 *  un navigateur n'efface un cookie que si les attributs correspondent. */
export function attributsCookieSession(maxAge: number) {
  return {
    httpOnly: true,
    sameSite: 'lax' as const,
    secure: EN_PROD,
    path: '/',
    maxAge,
  }
}

export const COOKIE_ADRESSE = 'jobbot_adresse_en_cours'

/** L'adresse en cours de vérification : elle transite par cookie et JAMAIS par
 *  l'URL, qui la ferait entrer dans l'historique, le Referer et les journaux. */
export function attributsCookieAdresse() {
  return {
    httpOnly: true,
    sameSite: 'lax' as const,
    secure: EN_PROD,
    path: '/',
    maxAge: 15 * 60,
  }
}
```

- [ ] **Step 4 : `web/app/api-client.ts`** — la couche réseau

```ts
// LE SEUL module qui parle à l'API. Aucun `fetch` ailleurs dans web/.
// C'est le pendant de « le LLM n'est appelé que depuis llm/client.py » (§9).

import { cookies, headers } from 'next/headers'

import {
  ErreurApi,
  NOM_COOKIE,
  ipCliente,
  lireCookieSession,
  type CookieSession,
  type PageOffres,
  type Utilisateur,
} from './api-contrat'

const BASE = process.env.API_BASE_URL ?? 'http://api:8080'

async function appeler(chemin: string, init: RequestInit = {}): Promise<Response> {
  const magasin = await cookies()
  const entrants = await headers()
  const entetes = new Headers(init.headers)
  entetes.set('Accept', 'application/json')

  const session = magasin.get(NOM_COOKIE)
  if (session) entetes.set('Cookie', `${NOM_COOKIE}=${session.value}`)

  const ip = ipCliente(entrants)
  if (ip) entetes.set('X-Forwarded-For', ip)

  const reponse = await fetch(`${BASE}${chemin}`, {
    ...init,
    headers: entetes,
    cache: 'no-store',
  })

  if (!reponse.ok) {
    let code = 'defaut'
    try {
      code = ((await reponse.json()) as { erreur?: string }).erreur ?? 'defaut'
    } catch {
      // Corps non-JSON : on garde le code par défaut.
    }
    const retry = reponse.headers.get('retry-after')
    throw new ErreurApi(code, reponse.status, retry ? Number(retry) : undefined)
  }
  return reponse
}

function corpsJson(donnees: unknown): RequestInit {
  return {
    method: 'POST',
    body: JSON.stringify(donnees),
    headers: { 'Content-Type': 'application/json' },
  }
}

export async function demanderCode(adresse: string): Promise<void> {
  await appeler('/auth/code/demande', corpsJson({ email: adresse }))
}

export async function verifierCode(
  adresse: string,
  code: string,
  nomComplet?: string,
): Promise<{ utilisateur: Utilisateur; session: CookieSession | null }> {
  const reponse = await appeler(
    '/auth/code/verifie',
    corpsJson({ email: adresse, code, nom_complet: nomComplet ?? null }),
  )
  return {
    utilisateur: (await reponse.json()) as Utilisateur,
    session: lireCookieSession(reponse.headers),
  }
}

export async function moi(): Promise<Utilisateur | null> {
  try {
    return (await (await appeler('/moi')).json()) as Utilisateur
  } catch (erreur) {
    if (erreur instanceof ErreurApi && erreur.statut === 401) return null
    throw erreur
  }
}

export async function listerOffres(limite = 20, decalage = 0): Promise<PageOffres> {
  const reponse = await appeler(`/offres?limite=${limite}&decalage=${decalage}`)
  return (await reponse.json()) as PageOffres
}

export async function deconnecter(): Promise<void> {
  await appeler('/auth/deconnexion', { method: 'POST' })
}
```

> Les tâches 6 et 7 importent `COOKIE_ADRESSE`, `attributsCookieAdresse`,
> `attributsCookieSession` et `ErreurApi` depuis **`api-contrat`**, et les fonctions réseau
> (`demanderCode`, `verifierCode`, `moi`, `listerOffres`, `deconnecter`) depuis **`api-client`**.

- [ ] **Step 5 : Écrire les tests — `web/test/api-contrat.test.ts`**

```ts
import { test } from 'node:test'
import assert from 'node:assert/strict'

import { ipCliente, lireCookieSession, attributsCookieSession } from '../app/api-contrat.ts'
import { texteErreur, ERREURS } from '../app/textes.ts'

test("ipCliente ne garde que la première IP de la chaîne", () => {
  const entetes = new Headers({ 'x-forwarded-for': '41.82.1.9, 172.18.0.4, 10.0.0.2' })
  assert.equal(ipCliente(entetes), '41.82.1.9')
})

test("ipCliente rend null quand l'en-tête est absent", () => {
  assert.equal(ipCliente(new Headers()), null)
})

test('lireCookieSession extrait la valeur et le max-age', () => {
  const entetes = new Headers()
  entetes.append(
    'set-cookie',
    'jobbot_session=abc.def.ghi; Max-Age=2592000; Path=/; HttpOnly; SameSite=lax',
  )
  const session = lireCookieSession(entetes)
  assert.equal(session?.valeur, 'abc.def.ghi')
  assert.equal(session?.maxAge, 2592000)
})

test('lireCookieSession ignore un cookie qui ne porte pas le bon nom', () => {
  const entetes = new Headers()
  entetes.append('set-cookie', 'autre=valeur; Path=/')
  assert.equal(lireCookieSession(entetes), null)
})

test('le cookie de session reste httpOnly et SameSite=lax', () => {
  const a = attributsCookieSession(2592000)
  assert.equal(a.httpOnly, true)
  assert.equal(a.sameSite, 'lax')
  assert.equal(a.path, '/')
  assert.equal(a.maxAge, 2592000)
})

test('chaque code d’erreur de l’API a une phrase', () => {
  for (const code of [
    'adresse_invalide',
    'trop_de_demandes',
    'plafond_global_atteint',
    'envoi_impossible',
    'code_invalide',
    'code_expire',
    'inscription_incomplete',
    'nom_invalide',
    'jeton_invalide',
  ]) {
    assert.ok(ERREURS[code], `code sans texte : ${code}`)
  }
})

test('un code inconnu tombe sur le message par défaut, jamais sur le code brut', () => {
  assert.equal(texteErreur('code_invente_par_un_attaquant'), ERREURS.defaut)
  assert.equal(texteErreur(undefined), null)
})
```

- [ ] **Step 6 : Lancer les tests web**

```bash
cd web && npm test
```

Attendu : les 7 tests passent.

- [ ] **Step 7 : Écrire le garde-fou côté Python — `tests/test_textes_web.py`**

```python
"""Chaque erreur métier doit avoir une phrase dans le client web.

Sans ce test, le jour où quelqu'un ajoute une dixième erreur côté Python,
l'utilisateur verrait un message générique sans que personne ne s'en aperçoive.
C'est le seul lien vérifié entre les deux langages du dépôt.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.core.erreurs import ErreurMetier

TEXTES = Path("web/app/textes.ts")


def _codes_metier() -> set[str]:
    trouves: set[str] = set()

    def descendre(classe: type[ErreurMetier]) -> None:
        trouves.add(classe.code)
        for fille in classe.__subclasses__():
            descendre(fille)

    descendre(ErreurMetier)
    return trouves


def _codes_du_web() -> set[str]:
    source = TEXTES.read_text(encoding="utf-8")
    bloc = re.search(r"export const ERREURS[^{]*\{(.*?)\n\}", source, re.S)
    assert bloc, "le bloc ERREURS est introuvable dans textes.ts"
    return set(re.findall(r"^\s*([a-z_]+):", bloc.group(1), re.M))


def test_chaque_erreur_metier_a_une_phrase_dans_le_web() -> None:
    manquants = _codes_metier() - _codes_du_web()
    assert not manquants, f"codes sans texte utilisateur : {sorted(manquants)}"


def test_le_web_porte_un_message_par_defaut() -> None:
    """Un code inconnu ne doit jamais s'afficher tel quel à l'utilisateur."""
    assert "defaut" in _codes_du_web()
```

- [ ] **Step 8 : Lancer, vérifier que tout passe**

```bash
pytest tests/test_textes_web.py -v
cd web && npm run typecheck && npm test
```

- [ ] **Step 9 : Commit**

```bash
git add web/app/api-contrat.ts web/app/api-client.ts web/app/textes.ts web/app/journal.ts \
        web/test/api-contrat.test.ts tests/test_textes_web.py
git commit -m "feat(web): contrat d'API, couche réseau, textes et journal de parcours"
```

---

## Task 6 : les deux écrans de connexion

**Files:**
- Create: `web/app/connexion/page.tsx`, `web/app/connexion/actions.ts`
- Create: `web/app/connexion/code/page.tsx`, `web/app/connexion/code/actions.ts`

**Interfaces:**
- Consomme : tout ce que produit la tâche 5.
- Produit : le parcours `/connexion` → `/connexion/code` → `/offres`.

### Le piège de `redirect()` dans un `try`

`redirect()` de Next **fonctionne en levant une exception** (`NEXT_REDIRECT`) que le framework
intercepte plus haut. L'appeler à l'intérieur d'un `try { } catch { }` fait avaler la redirection
par le `catch` : la page ne redirige pas, et l'erreur affichée n'a aucun rapport.

**Règle sans exception dans ce dépôt : `redirect()` s'appelle toujours APRÈS le bloc `try`.**
On mémorise le code d'erreur dans une variable, et on redirige ensuite.

- [ ] **Step 1 : `web/app/connexion/actions.ts`**

```ts
'use server'

import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

import { COOKIE_ADRESSE, ErreurApi, attributsCookieAdresse } from '../api-contrat'
import { demanderCode } from '../api-client'
import { journaliser } from '../journal'

export async function envoyerCode(formData: FormData): Promise<void> {
  const adresse = String(formData.get('adresse') ?? '').trim()

  if (!adresse) redirect('/connexion?erreur=adresse_invalide')

  // redirect() lève une exception interceptée par Next : jamais dans un try.
  let echec: string | null = null
  try {
    await demanderCode(adresse)
    const magasin = await cookies()
    magasin.set(COOKIE_ADRESSE, adresse, attributsCookieAdresse())
  } catch (erreur) {
    if (erreur instanceof ErreurApi) echec = erreur.code
    else throw erreur
  }

  if (echec) {
    journaliser('adresse_refusee', { code: echec })
    redirect(`/connexion?erreur=${encodeURIComponent(echec)}`)
  }

  journaliser('code_demande')
  redirect('/connexion/code')
}
```

- [ ] **Step 2 : `web/app/connexion/page.tsx`**

```tsx
import { texteErreur, T } from '../textes'
import { envoyerCode } from './actions'

export default async function PageConnexion({
  searchParams,
}: {
  searchParams: Promise<{ erreur?: string }>
}) {
  const { erreur } = await searchParams
  const message = texteErreur(erreur)

  return (
    <main>
      <h1>{T.titreAdresse}</h1>
      <p>{T.aideAdresse}</p>
      {message && <p className="erreur">{message}</p>}
      <form action={envoyerCode}>
        <label htmlFor="adresse">{T.champAdresse}</label>
        <input
          id="adresse"
          name="adresse"
          type="email"
          inputMode="email"
          autoComplete="email"
          required
        />
        <button type="submit">{T.boutonAdresse}</button>
      </form>
    </main>
  )
}
```

- [ ] **Step 3 : `web/app/connexion/code/actions.ts`**

```ts
'use server'

import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

import { COOKIE_ADRESSE, ErreurApi, attributsCookieSession } from '../../api-contrat'
import { verifierCode } from '../../api-client'
import { journaliser } from '../../journal'

export async function validerCode(formData: FormData): Promise<void> {
  const magasin = await cookies()
  const adresse = magasin.get(COOKIE_ADRESSE)?.value

  // Le cookie a expiré (15 min) ou l'utilisateur est arrivé là directement.
  if (!adresse) redirect('/connexion?erreur=code_expire')

  const code = String(formData.get('code') ?? '').trim()
  const nom = String(formData.get('nom') ?? '').trim()

  let echec: string | null = null
  try {
    const { session } = await verifierCode(adresse, code, nom || undefined)
    if (session) {
      magasin.set(session.nom, session.valeur, attributsCookieSession(session.maxAge))
    }
    magasin.delete(COOKIE_ADRESSE)
  } catch (erreur) {
    if (erreur instanceof ErreurApi) echec = erreur.code
    else throw erreur
  }

  // Ce n'est pas une erreur mais un aiguillage : le compte est nouveau, donc
  // l'API réclame un nom. Elle a redéposé le code, il reste valide.
  if (echec === 'inscription_incomplete' || echec === 'nom_invalide') {
    journaliser('nom_demande')
    redirect(`/connexion/code?nom=requis&erreur=${encodeURIComponent(echec)}`)
  }

  if (echec) {
    journaliser('code_refuse', { code: echec })
    redirect(`/connexion/code?erreur=${encodeURIComponent(echec)}`)
  }

  journaliser('connexion_reussie')
  redirect('/offres')
}
```

> **Attention :** `nom_invalide` renvoie sur l'écran avec le champ nom, et **pas** vers
> `/connexion`. L'API a redéposé le code : renvoyer l'utilisateur au début lui ferait redemander
> un email, attendre le délai de garde et entamer son quota d'envois. Le commentaire de
> `routers/auth.py` le dit explicitement, et le §11 du brief rappelle que l'abandon en onboarding
> est le risque principal.

- [ ] **Step 4 : `web/app/connexion/code/page.tsx`**

```tsx
import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

import { COOKIE_ADRESSE } from '../../api-contrat'
import { texteErreur, T } from '../../textes'
import { validerCode } from './actions'

export default async function PageCode({
  searchParams,
}: {
  searchParams: Promise<{ erreur?: string; nom?: string }>
}) {
  const magasin = await cookies()
  if (!magasin.get(COOKIE_ADRESSE)) redirect('/connexion')

  const { erreur, nom } = await searchParams
  const message = texteErreur(erreur)
  const nomRequis = nom === 'requis'

  return (
    <main>
      <h1>{T.titreCode}</h1>
      <p>{T.aideCode}</p>
      {message && <p className="erreur">{message}</p>}
      <form action={validerCode}>
        <label htmlFor="code">{T.champCode}</label>
        <input
          id="code"
          name="code"
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          required
        />
        {nomRequis && (
          <>
            <p>{T.aideNom}</p>
            <label htmlFor="nom">{T.champNom}</label>
            <input id="nom" name="nom" type="text" autoComplete="name" required />
          </>
        )}
        <button type="submit">{T.boutonCode}</button>
      </form>
    </main>
  )
}
```

- [ ] **Step 5 : Vérifier les types et le build**

```bash
cd web && npm run typecheck && npm run build
```

- [ ] **Step 6 : Mesurer le poids de la page d'inscription — le critère de la phase**

```bash
cd web && npm start &
sleep 5 && npm run mesure -- /connexion
```

Attendu : **sous 200 Ko**, et le script sort en succès. S'il sort en échec, **ne pas continuer** :
c'est le critère de validation de la phase qui tombe. Le premier levier est le nombre de
fragments JS chargés, pas la feuille de style.

- [ ] **Step 7 : Commit**

```bash
git add web/app/connexion/
git commit -m "feat(web): écrans de saisie de l'adresse et du code"
```

---

## Task 7 : offres, compte, déconnexion et page racine

**Files:**
- Create: `web/app/offres/page.tsx`
- Create: `web/app/compte/page.tsx`, `web/app/compte/actions.ts`
- Modify: `web/app/page.tsx` (remplacer le contenu temporaire de la tâche 4)

**Interfaces:**
- Consomme : `moi()`, `listerOffres()`, `deconnecter()` de la tâche 5 ; `GET /offres` des
  tâches 1 et 2.

- [ ] **Step 1 : `web/app/page.tsx`** (remplace le contenu temporaire)

```tsx
import { redirect } from 'next/navigation'

import { moi } from './api-client'

export default async function PageRacine() {
  const utilisateur = await moi()
  redirect(utilisateur ? '/offres' : '/connexion')
}
```

- [ ] **Step 2 : `web/app/offres/page.tsx`**

```tsx
import { redirect } from 'next/navigation'

import { listerOffres, moi } from '../api-client'
import type { Offre } from '../api-contrat'
import { T } from '../textes'

function commentPostuler(methode: string): string {
  if (methode === 'email') return T.parEmail
  if (methode === 'form') return T.parFormulaire
  return T.parSiteExterne
}

function LigneOffre({ offre }: { offre: Offre }) {
  const details = [offre.entreprise, offre.lieu, offre.type_contrat].filter(Boolean).join(' · ')
  return (
    <li className="offre">
      <h2>{offre.titre}</h2>
      {details && <p className="meta">{details}</p>}
      <p className="meta">{commentPostuler(offre.methode_candidature)}</p>
      <a href={offre.url} rel="noopener noreferrer" target="_blank">
        {T.voirOffre}
      </a>
    </li>
  )
}

export default async function PageOffres() {
  const utilisateur = await moi()
  if (!utilisateur) redirect('/connexion')

  const page = await listerOffres(20, 0)

  return (
    <main>
      <nav>
        <a href="/compte">{T.lienCompte}</a>
      </nav>
      <h1>{T.titreOffres}</h1>
      {page.offres.length === 0 ? (
        <p>{T.aucuneOffre}</p>
      ) : (
        <ul style={{ listStyle: 'none', padding: 0 }}>
          {page.offres.map((offre) => (
            <LigneOffre key={offre.id} offre={offre} />
          ))}
        </ul>
      )}
    </main>
  )
}
```

- [ ] **Step 3 : `web/app/compte/actions.ts`**

```ts
'use server'

import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

import { ErreurApi, NOM_COOKIE } from '../api-contrat'
import { deconnecter } from '../api-client'
import { journaliser } from '../journal'

export async function seDeconnecter(): Promise<void> {
  try {
    await deconnecter()
  } catch (erreur) {
    // Une session déjà invalide n'empêche pas de se déconnecter : c'est
    // exactement ce que l'utilisateur demande.
    if (!(erreur instanceof ErreurApi)) throw erreur
  }

  // L'API efface son cookie, mais c'est nous qui l'avons posé : il faut
  // l'effacer ici aussi. La révocation réelle tient à `token_version` côté
  // base, pas à la disparition du cookie.
  const magasin = await cookies()
  magasin.delete(NOM_COOKIE)

  journaliser('deconnexion')
  redirect('/connexion')
}
```

- [ ] **Step 4 : `web/app/compte/page.tsx`**

```tsx
import { redirect } from 'next/navigation'

import { moi } from '../api-client'
import { T } from '../textes'
import { seDeconnecter } from './actions'

export default async function PageCompte() {
  const utilisateur = await moi()
  if (!utilisateur) redirect('/connexion')

  return (
    <main>
      <nav>
        <a href="/offres">{T.lienOffres}</a>
      </nav>
      <h1>{T.titreCompte}</h1>
      <p>
        {utilisateur.nom_complet ?? ''}
        <br />
        {utilisateur.email}
      </p>
      <form action={seDeconnecter}>
        <button type="submit">{T.boutonDeconnexion}</button>
      </form>
    </main>
  )
}
```

- [ ] **Step 5 : Vérifier types et build**

```bash
cd web && npm run typecheck && npm run build && npm test
```

- [ ] **Step 6 : Commit**

```bash
git add web/app/page.tsx web/app/offres/ web/app/compte/
git commit -m "feat(web): liste des offres, écran de compte et déconnexion"
```

---

## Task 8 : image Docker, parcours réel, et mise à jour du CLAUDE.md

**Files:**
- Create: `web/Dockerfile`
- Modify: `CLAUDE.md` (§4, §11, §12)

**Interfaces:** aucune — tâche de clôture.

- [ ] **Step 1 : `web/Dockerfile`**

```dockerfile
# Build multi-étapes : l'image finale ne porte pas les node_modules de build.
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

FROM node:24-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:24-alpine AS run
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
# `output: "standalone"` produit un serveur autonome et sa liste minimale de
# modules : l'image ne porte ni les sources, ni les dépendances de build.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
```

> Si `web/public/` n'existe pas, créer `web/public/.gitkeep` : sans le dossier, le `COPY` échoue.

- [ ] **Step 2 : Construire et lancer la pile complète**

```bash
docker compose build web
docker compose up -d postgres redis
docker compose run --rm migrate
docker compose up -d api web
docker compose ps
```

> ⚠️ **Jamais `docker compose down -v`.** Le volume `pgdata` porte 232 offres réelles.

- [ ] **Step 3 : Dérouler le parcours réel, de bout en bout**

Dans un navigateur, sur `http://127.0.0.1:3000` :

1. La racine redirige vers `/connexion`.
2. Saisir une adresse. Récupérer le code dans les journaux de l'API — c'est la raison d'être du
   fournisseur `console` en développement :
   ```bash
   docker compose logs api | grep -i code | tail -5
   ```
3. Saisir le code. Le compte étant nouveau, l'écran doit **réafficher le champ code et ajouter
   un champ nom**, sans redemander d'email.
4. Saisir le nom → arrivée sur `/offres`, qui liste de vraies offres.
5. `/compte` affiche l'adresse et le nom. « Se déconnecter » renvoie sur `/connexion`.
6. Revenir sur `/offres` : doit rediriger vers `/connexion`.

- [ ] **Step 4 : Vérifier que le rafraîchissement s'est bien déclenché**

```bash
docker compose logs api | grep rafraichissement_demande | tail -5
```

Attendu : une ligne par source. Une seconde visite immédiate doit donner une `raison` indiquant
que la passe est encore fraîche, **pas** relancer un scraping.

- [ ] **Step 5 : Mesurer le poids en conditions réelles, et le doubler en vrai navigateur**

```bash
cd web && URL_BASE=http://127.0.0.1:3000 npm run mesure -- /connexion
```

Puis ouvrir l'onglet Réseau du navigateur sur `/connexion`, **cache vidé**, et comparer le total
transféré au chiffre du script. Les deux doivent concorder à quelques kilooctets près. **S'ils
divergent nettement, c'est le script qui a tort** — il ne voit pas les fragments dynamiques — et
il faut le dire au porteur du projet plutôt que de retenir le chiffre le plus favorable.

**Consigner les deux chiffres dans le message de commit.**

- [ ] **Step 6 : Mettre à jour le CLAUDE.md**

1. **§11** — remplacer « polices locales via `next/font` » par :
   ```
   - Police **système** (`system-ui`), pas de fichier de police téléchargé : zéro octet
     transféré et aucun saut de mise en page au chargement. Révise le 2026-09-13 la consigne
     « polices locales via next/font », qui coûtait 15 à 40 Ko sur un budget de 200 Ko.
   ```
2. **§4** — remplacer les trois lignes de `web/` par l'arborescence réelle, et ajouter sous
   `src/api/` : `routers/offres.py` et `schemas/offres.py`.
3. **§12, Phase 2** — ajouter sous les critères de validation :
   ```
   > Les quatre critères passent depuis le 2026-09-13. Le client web existe, le critère 4 est
   > mesuré par `web/mesure-poids.mjs` et doublé en vrai navigateur.
   ```

- [ ] **Step 7 : Suite complète**

```bash
pytest -q
RUN_INTEGRATION_TESTS=1 pytest -m integration -q
mypy --strict src
ruff check src tests
cd web && npm run typecheck && npm test && npm run build
```

Attendu : tout au vert. **Si un test échoue, ne pas déclarer la phase finie.**

- [ ] **Step 8 : Commit**

```bash
git add web/Dockerfile web/public/.gitkeep CLAUDE.md
git commit -m "feat(web): image Docker, et mise à jour du brief (§4, §11, §12)"
```

---

## Après le plan

Le §14.9 du CLAUDE.md — **par quel canal pousser les alertes offres** — reste ouvert et **bloque
la Phase 4**. La liste consultable écrite ici n'y répond pas : consulter n'est pas être alerté.
Le poser au porteur du projet avant d'attaquer la Phase 4, pas pendant.
