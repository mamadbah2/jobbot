# Retrait de Telegram et du téléphone — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Supprimer Telegram comme client du produit et retirer le numéro de téléphone de la table d'identité, en remplaçant le canal d'alerte administrateur qui passait par Telegram.

**Architecture :** huit tâches, chacune verte à sa fin. On retire de l'extérieur vers l'intérieur : d'abord le client Telegram (rien ne l'importe), puis l'endpoint de liaison, puis la couche métier, puis le schéma de base. Le canal d'alerte par email arrive avant le nettoyage de la configuration, parce qu'il remplace `ADMIN_TELEGRAM_ID` au moment où celui-ci disparaît. La documentation est réécrite en avant-dernier, la vérification de bout en bout en dernier.

**Tech Stack :** Python 3.11, FastAPI, SQLAlchemy 2.0 async, Alembic, Redis, pydantic-settings, structlog, pytest + pytest-asyncio, ruff, mypy --strict.

**Spec :** `docs/superpowers/specs/2026-09-12-retrait-telegram-design.md`

---

## Global Constraints

- **Branche : `worktree-phase2-socle-backend`**, dans le worktree `/home/mamadbah/projects/jobbot/.claude/worktrees/phase2-socle-backend`. Ne jamais travailler depuis le dépôt principal.
- **L'interpréteur est `.venv/bin/python` du worktree.** Son `.pth` éditable pointe sur le worktree ; utiliser le venv du dépôt principal ferait tester le mauvais code.
- **La base de développement est PARTAGÉE avec le dépôt principal et porte 232 offres réelles.** Ne jamais exécuter `docker compose down -v`, ni `alembic downgrade`, ni `DROP DATABASE`. Vérifier `select count(*) from jobs` = 232 avant et après toute migration.
- **`docker compose` ne fonctionne pas depuis le worktree** : `.env` est gitignoré, donc absent ici. Pour lire la base, utiliser `docker exec jobbot-postgres-1 psql -U jobbot -d jobbot -c '…'`. Pour lancer la pile, se placer dans le dépôt principal.
- **État de départ : la branche est ROUGE, pytest ET mypy.** `pytest -q` donne `334 passed, 2 failed` ; `mypy src/` donne `Unexpected keyword argument "telephone_saisi" for "lier_telegram"` à `src/bot/handlers/compte.py:75` (57 fichiers vérifiés). Les deux viennent des commits non poussés qui ont retiré la recherche par numéro de `lier_telegram` sans réaligner son appelant, et les deux disparaissent avec `src/bot/` en Tâche 1. Les deux échecs pytest sont `tests/test_bot_compte.py::test_numero_etranger_normalisation_reelle_ne_touche_pas_la_base[hors_senegal]` et `[invalide_sans_indicatif_senegalais]`. Ne pas chercher à réparer l'un ou l'autre : c'est du travail sur du code condamné.
- Type hints partout. `mypy --strict` doit passer sur `src/` (`files = ["src"]`).
- `ruff check src/ tests/` doit passer. Longueur de ligne : 100.
- Aucun `print()` : `structlog` uniquement, via `src.logging_setup.get_logger`.
- Aucune dépendance ajoutée. Ce plan n'en retire que deux.
- Tous les textes, commentaires, docstrings et messages de commit en **français**.
- Messages de commit au format `type(portée): sujet`, et terminés par :
  ```
  Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01Sep8DxRJusdAs9r2zWaZCk
  ```
- Aucune migration par `create_all` : Alembic uniquement.
- Les tests unitaires ne touchent ni le réseau ni la base. Les tests marqués `integration` ont besoin de Postgres sur `localhost:55432` et se lancent par `RUN_INTEGRATION_TESTS=1 .venv/bin/python -m pytest -m integration`.

---

## Structure des fichiers

**Supprimés :**

| Chemin | Rôle qui disparaît |
|---|---|
| `src/bot/__init__.py`, `main.py`, `keyboards.py`, `texts.py` | Client Telegram : démarrage, claviers, textes utilisateur |
| `src/bot/handlers/__init__.py`, `start.py`, `compte.py` | Handlers `/start`, `/aide`, liaison par contact |
| `src/core/telephone.py` | Normalisation E.164 sénégalaise |
| `tests/test_bot_compte.py`, `tests/test_bot_start.py`, `tests/test_telephone.py` | Leurs tests |

**Créés :**

| Chemin | Responsabilité |
|---|---|
| `tests/test_retrait_telegram_telephone.py` | Garde anti-retour : Telegram et le téléphone ne peuvent pas revenir par un import isolé sans qu'un test le dise |
| `alembic/versions/0005_retrait_telephone_telegram.py` | `DROP COLUMN phone`, `DROP COLUMN telegram_id` |

**Modifiés :** `pyproject.toml`, `docker-compose.yml`, `.env.example`, `README.md`, `CLAUDE.md`, `src/config.py`, `src/logging_setup.py`, `src/alerting.py`, `src/courriel/provider.py`, `src/courriel/console.py`, `src/core/erreurs.py`, `src/core/alerte.py`, `src/core/auth/cles.py`, `src/core/auth/comptes.py`, `src/api/app.py`, `src/api/routers/moi.py`, `src/api/routers/auth.py`, `src/api/schemas/auth.py`, `src/db/models.py`, `docs/superpowers/specs/2026-09-11-socle-backend-design.md`, et onze fichiers de `tests/`.

---

## Task 1 : supprimer le client Telegram

**Files:**
- Delete: `src/bot/` (7 fichiers), `tests/test_bot_compte.py`, `tests/test_bot_start.py`
- Create: `tests/test_retrait_telegram_telephone.py`
- Modify: `pyproject.toml:4,8`, `docker-compose.yml:74-79`, `src/logging_setup.py:57-62`

**Interfaces:**
- Consomme : rien.
- Produit : `tests/test_retrait_telegram_telephone.py`, le fichier de gardes auquel les Tâches 2, 3 et 6 ajoutent les leurs. Ce qu'elles en consomment, ce sont ses imports de tête (`tomllib`, `Path`) et son existence — **pas** ses helpers `_fichiers_src()` / `_modules_importes()`, qui ne servent qu'aux deux tests de cette tâche.

- [ ] **Step 1 : écrire le test qui échoue**

Créer `tests/test_retrait_telegram_telephone.py` :

```python
"""Garde anti-retour du retrait du 2026-09-12.

Telegram et le numéro de téléphone ont été retirés du produit (spec
`docs/superpowers/specs/2026-09-12-retrait-telegram-design.md`). Sans ces
tests, ils peuvent revenir par un import isolé, un réglage rajouté ou une
fonction ressuscitée, sans que rien ne le signale : c'est précisément ce
genre de retour silencieux qu'aucun test fonctionnel ne voit.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

RACINE_SRC = Path("src")


def _fichiers_src() -> list[Path]:
    fichiers = sorted(RACINE_SRC.rglob("*.py"))
    assert len(fichiers) >= 30, "arborescence src/ introuvable : le test serait creux"
    return fichiers


def _modules_importes(fichier: Path) -> set[str]:
    arbre = ast.parse(fichier.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module and noeud.level == 0:
            modules.add(noeud.module.split(".")[0])
    return modules


def test_aucun_module_de_src_n_importe_aiogram() -> None:
    fautifs = [str(f) for f in _fichiers_src() if "aiogram" in _modules_importes(f)]
    assert not fautifs, f"aiogram est de retour dans : {fautifs}"


def test_aiogram_n_est_plus_une_dependance_declaree() -> None:
    """Retirer les imports sans retirer la dépendance laisserait l'image Docker
    la télécharger et un futur import passer inaperçu."""
    projet = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    declarees = " ".join(projet["project"]["dependencies"]).lower()
    assert "aiogram" not in declarees


def test_le_paquet_du_bot_n_existe_plus() -> None:
    assert not Path("src/bot").exists(), "src/bot/ est de retour"
```

- [ ] **Step 2 : lancer le test pour vérifier qu'il échoue**

Run: `.venv/bin/python -m pytest tests/test_retrait_telegram_telephone.py -v`
Expected: les trois tests ÉCHOUENT. `test_aucun_module_de_src_n_importe_aiogram` liste les fichiers de `src/bot/` ; `test_aiogram_n_est_plus_une_dependance_declaree` échoue sur `aiogram>=3.13` ; `test_le_paquet_du_bot_n_existe_plus` échoue sur l'existence de `src/bot`.

- [ ] **Step 3 : supprimer le paquet du bot et ses tests**

```bash
git rm -r src/bot
git rm tests/test_bot_compte.py tests/test_bot_start.py
```

- [ ] **Step 4 : retirer la dépendance `aiogram` et corriger la description du projet**

Dans `pyproject.toml`, supprimer la ligne `    "aiogram>=3.13",` et remplacer la ligne 4 :

```toml
description = "JobBot Sénégal — candidature assistée pour le marché de l'emploi sénégalais."
```

- [ ] **Step 5 : retirer le service `bot` du Docker Compose**

Supprimer le bloc complet (`docker-compose.yml:74-79`) :

```yaml
  bot:
    <<: *app
    command: ["python", "-m", "src.bot.main"]
    # Plus de `ports` ni de `healthcheck` : depuis le 2026-09-11 le bot ne sert
    # plus de HTTP, c'est le service `api` qui porte /health (CLAUDE.md §4).
    depends_on: *depends_app
```

- [ ] **Step 6 : retirer le commentaire `aiogram.event` de la configuration des logs**

Dans `src/logging_setup.py`, supprimer les six lignes de commentaire qui commencent par `# - \`aiogram.event\` journalise lui aussi les exceptions` et se terminent par `#   trace. Un no-op trompeur : pas ajouté ici, signalé dans le rapport.`. **Ne pas toucher** à la ligne `logging.getLogger("uvicorn.error").addFilter(SansTrace())` qui suit : c'est le seul filtre réel, et il reste.

- [ ] **Step 7 : lancer les tests pour vérifier qu'ils passent**

Run: `.venv/bin/python -m pytest -q`
Expected: `336 passed` — les 3 nouveaux tests passent, et les 2 échecs de `tests/test_bot_compte.py` ont disparu avec le fichier. La suite redevient verte.

- [ ] **Step 8 : vérifier ruff et mypy**

Run: `.venv/bin/python -m ruff check src/ tests/ && .venv/bin/python -m mypy src/`
Expected: `All checks passed` et `Success` sur 50 fichiers (7 de moins qu'avant).

- [ ] **Step 9 : commit**

```bash
git add -A
git commit -m "$(cat <<'MSG'
feat(bot): supprimer le client Telegram

Décision du porteur du projet le 2026-09-12 : Telegram cesse d'être un
client du produit, le web devient le seul client. Suppression et non
débranchement : du code mort que mypy, ruff et pytest continuent de
traiter est une charge permanente, et chaque session future le croirait
vivant.

Un test de garde interdit le retour d'aiogram par un import isolé ou par
la liste de dépendances.

Les deux tests de tests/test_bot_compte.py qui échouaient depuis le
retrait de la recherche par numéro dans lier_telegram disparaissent avec
le fichier : la suite redevient verte.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Sep8DxRJusdAs9r2zWaZCk
MSG
)"
```

---

## Task 2 : retirer l'endpoint de liaison Telegram

**Files:**
- Modify: `src/api/routers/moi.py` (réécriture complète), `src/core/auth/cles.py:1-21`, `src/core/erreurs.py:26,112-116`, `src/api/app.py:24,54`, `src/config.py:59`, `.env.example:88-89`, `tests/test_api_moi.py`, `tests/test_retrait_telegram_telephone.py`
- Test: `tests/test_api_moi.py`, `tests/test_retrait_telegram_telephone.py`

**Interfaces:**
- Consomme : les helpers de `tests/test_retrait_telegram_telephone.py` (Tâche 1).
- Produit : `src/api/routers/moi.py` ne conserve que `moi()`, qui rend `Utilisateur.depuis(utilisateur)`. `cles.Usage` devient `Literal["jeton", "code", "limite"]`.

- [ ] **Step 1 : écrire les tests qui échouent**

Ajouter à la fin de `tests/test_retrait_telegram_telephone.py` :

```python
def test_l_usage_de_cle_liaison_n_existe_plus() -> None:
    """`cles.Usage` est un `Literal` : mypy seul le contrôle, et mypy ne tourne
    pas en CI de test. Sans cette assertion, `deriver(secret, "liaison")`
    resterait écrivable à l'exécution."""
    from typing import get_args

    from src.core.auth import cles

    assert "liaison" not in get_args(cles.Usage)


def test_aucun_reglage_de_liaison_telegram() -> None:
    from src.config import Settings

    assert "telegram_bot_username" not in Settings.model_fields
```

Ajouter à `tests/test_api_moi.py` :

```python
@pytest.mark.integration
def test_l_endpoint_de_liaison_telegram_n_existe_plus(client_auth: TestClient) -> None:
    """L'endpoint produisait un lien profond `t.me`. Il est retiré avec le bot ;
    un 404 plutôt qu'un 401 prouve que la route elle-même a disparu, et pas
    seulement son autorisation."""
    assert client_auth.post("/moi/telegram/jeton").status_code == 404
```

- [ ] **Step 2 : lancer les tests pour vérifier qu'ils échouent**

Run: `.venv/bin/python -m pytest tests/test_retrait_telegram_telephone.py -v && RUN_INTEGRATION_TESTS=1 .venv/bin/python -m pytest -m integration "tests/test_api_moi.py::test_l_endpoint_de_liaison_telegram_n_existe_plus" -v`
Expected: `test_l_usage_de_cle_liaison_n_existe_plus` ÉCHOUE (`"liaison"` est dans `get_args`), `test_aucun_reglage_de_liaison_telegram` ÉCHOUE, et le test d'intégration ÉCHOUE avec `assert 401 == 404` — 401 et non 200, parce que la route existe encore et exige une session ; c'est précisément ce que le test doit distinguer d'un 404.

- [ ] **Step 3 : réécrire `src/api/routers/moi.py`**

Remplacer tout le fichier par :

```python
"""Compte courant (spec Phase 2 §9).

L'endpoint de liaison Telegram (`POST /moi/telegram/jeton`) a été retiré le
2026-09-12 avec le client Telegram, ainsi que sa mécanique de jeton à usage
unique en Redis : plus de bot à relier, plus de lien profond à produire.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from src.api import deps
from src.api.schemas.auth import Utilisateur
from src.db.models import User

router = APIRouter(tags=["moi"])


@router.get("/moi")
async def moi(
    utilisateur: Annotated[User, Depends(deps.utilisateur_courant)],
) -> Utilisateur:
    return Utilisateur.depuis(utilisateur)
```

- [ ] **Step 4 : retirer l'usage `liaison` de la dérivation de clés**

Dans `src/core/auth/cles.py`, remplacer la ligne 21 par :

```python
Usage = Literal["jeton", "code", "limite"]
```

et, dans la docstring du module, remplacer les lignes 3 à 7 par :

```
Un seul `JWT_SECRET` est fourni par l'exploitant, mais il alimente trois usages
cryptographiques distincts : la signature des jetons, le hachage des codes de
vérification et celui des clés de limitation. Les employer bruts ferait qu'une
faiblesse découverte sur l'un compromettrait les autres.
```

- [ ] **Step 5 : retirer `LiaisonIndisponible`**

Dans `src/core/erreurs.py` : supprimer `"LiaisonIndisponible",` de `__all__` (ligne 26) et la classe des lignes 112-116.

Dans `src/api/app.py` : supprimer `LiaisonIndisponible,` de l'import (ligne 24) et la ligne `    LiaisonIndisponible: status.HTTP_503_SERVICE_UNAVAILABLE,` du dictionnaire `_STATUTS` (ligne 54).

- [ ] **Step 6 : retirer le réglage du nom du bot**

Dans `src/config.py`, supprimer la ligne 59 `    telegram_bot_username: str = ""`.

Dans `.env.example`, supprimer les deux dernières lignes :

```
# Sans @ — sert à construire le lien profond de liaison de compte.
TELEGRAM_BOT_USERNAME=
```

- [ ] **Step 7 : supprimer les tests de l'endpoint retiré**

Dans `tests/test_api_moi.py` : supprimer les six tests de liaison (`test_jeton_de_liaison_telegram`, celui qui vérifie le 401 sans session sur cette route, celui du `TELEGRAM_BOT_USERNAME` vide, celui de la péremption du jeton précédent, et les deux derniers de la section), ainsi que le helper `_jeton_du_lien` et tout import devenu inutilisé. Adapter la docstring de tête du fichier :

```python
"""GET /moi et POST /auth/deconnexion (spec Phase 2 §9).

`POST /moi/telegram/jeton` a été retiré le 2026-09-12 avec le client Telegram.
"""
```

Conserver la classe espionne d'alertes si elle sert encore à d'autres tests du fichier ; sinon la supprimer aussi.

- [ ] **Step 8 : lancer la suite complète**

Run: `.venv/bin/python -m pytest -q && RUN_INTEGRATION_TESTS=1 .venv/bin/python -m pytest -m integration -q`
Expected: tout vert, zéro avertissement. Le compte unitaire MONTE de deux (les deux gardes) : les six tests de liaison retirés étaient tous marqués `integration`, c'est donc le compte d'intégration qui baisse.

- [ ] **Step 9 : vérifier ruff et mypy**

Run: `.venv/bin/python -m ruff check src/ tests/ && .venv/bin/python -m mypy src/`
Expected: `All checks passed` et `Success`.

- [ ] **Step 10 : commit**

```bash
git add -A
git commit -m "$(cat <<'MSG'
feat(api): retirer l'endpoint de liaison Telegram

Plus de bot à relier : POST /moi/telegram/jeton disparaît avec sa
mécanique de jeton à usage unique en Redis, l'usage de clé « liaison »,
l'exception LiaisonIndisponible et le réglage TELEGRAM_BOT_USERNAME.

La dérivation d'une clé par usage reste entière : c'est une propriété de
sécurité indépendante de Telegram, elle passe simplement de quatre
usages à trois.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Sep8DxRJusdAs9r2zWaZCk
MSG
)"
```

---

## Task 3 : retirer téléphone et telegram_id de la couche métier

**Files:**
- Delete: `src/core/telephone.py`, `tests/test_telephone.py`
- Modify: `src/core/auth/comptes.py` (réécriture complète), `src/core/erreurs.py`, `src/api/app.py`, `src/api/routers/auth.py:195-200`, `tests/test_auth_comptes.py`, `tests/test_retrait_telegram_telephone.py`
- Modify: `pyproject.toml:20` (retirer `phonenumbers`)

**Interfaces:**
- Consomme : les helpers de `tests/test_retrait_telegram_telephone.py` (Tâche 1).
- Produit : `src/core/auth/comptes.py` n'expose plus que `par_adresse(session, adresse) -> User | None`, `connecter_ou_inscrire(session, *, adresse, nom_complet=None) -> User` et `revoquer_jetons(session, utilisateur) -> None`. `src/core/erreurs.py` n'expose plus `NumeroInvalide`, `TelephoneDejaUtilise`, `ContactUsurpe`, `TelegramDejaLie`.

- [ ] **Step 1 : écrire les tests qui échouent**

Ajouter à `tests/test_retrait_telegram_telephone.py` :

```python
def test_le_module_de_normalisation_telephonique_n_existe_plus() -> None:
    assert not Path("src/core/telephone.py").exists()


def test_phonenumbers_n_est_plus_une_dependance_declaree() -> None:
    projet = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    declarees = " ".join(projet["project"]["dependencies"]).lower()
    assert "phonenumbers" not in declarees


def test_les_fonctions_telephone_et_telegram_ont_disparu_des_comptes() -> None:
    """Elles portaient la pose d'un numéro et la liaison d'un telegram_id sur un
    compte. Les ressusciter sans colonne les ferait échouer à l'exécution, pas
    à l'import : cette assertion est ce qui rend le retrait visible."""
    from src.core.auth import comptes

    for nom in ("par_telephone", "par_telegram", "lier_telegram", "definir_telephone"):
        assert not hasattr(comptes, nom), f"comptes.{nom} est de retour"


def test_les_exceptions_du_telephone_et_de_telegram_ont_disparu() -> None:
    from src.core import erreurs

    for nom in ("NumeroInvalide", "TelephoneDejaUtilise", "ContactUsurpe", "TelegramDejaLie"):
        assert not hasattr(erreurs, nom), f"erreurs.{nom} est de retour"
        assert nom not in erreurs.__all__
```

- [ ] **Step 2 : lancer les tests pour vérifier qu'ils échouent**

Run: `.venv/bin/python -m pytest tests/test_retrait_telegram_telephone.py -v`
Expected: les quatre nouveaux tests ÉCHOUENT.

- [ ] **Step 3 : réécrire `src/core/auth/comptes.py`**

Remplacer tout le fichier par :

```python
"""Comptes utilisateurs (spec Phase 2 §8 et §9).

Deux règles portent tout le reste :

1. **Un seul endpoint pour l'inscription et la reconnexion.** C'est ce qui permet
   à `/auth/code/demande` de répondre exactement pareil que l'adresse existe ou
   non : sans cela, l'endpoint dirait publiquement qui est client.
2. **Un compte existant ignore les champs fournis.** Sinon `/auth/code/verifie`
   deviendrait un moyen d'écraser le nom d'un compte existant.

Depuis le 2026-09-12, l'identité d'un compte est son adresse email, et rien
d'autre. Le numéro de téléphone a été retiré de `users` : le code à 6 chiffres
ne prouvait que la possession de l'adresse, jamais celle d'un numéro, et cette
confusion permettait de squatter le numéro d'autrui. Le numéro réapparaîtra en
Phase 3 dans `profiles.structured`, extrait du CV, sans prétention de
vérification. `telegram_id` est parti avec le client Telegram.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import courriel_valide
from src.core.erreurs import InscriptionIncomplete, NomInvalide
from src.core.saisie import texte_saisi
from src.db.models import User


async def par_adresse(session: AsyncSession, adresse: str) -> User | None:
    resultat = await session.execute(
        select(User).where(User.email == courriel_valide.normaliser(adresse))
    )
    return resultat.scalar_one_or_none()


async def connecter_ou_inscrire(
    session: AsyncSession,
    *,
    adresse: str,
    nom_complet: str | None = None,
) -> User:
    """Rend le compte existant, ou en crée un. L'adresse est déjà prouvée."""
    normalisee = courriel_valide.normaliser(adresse)

    existant = await par_adresse(session, normalisee)
    if existant is not None:
        return existant

    if not nom_complet:
        raise InscriptionIncomplete(InscriptionIncomplete.code)

    # `nom_complet` est une saisie utilisateur non fiable : borne de 255, taille
    # de la colonne `users.full_name` (§5). Un type inattendu (int, liste) doit
    # produire `NomInvalide`, jamais une `AttributeError` ni une `DataError`.
    nom = texte_saisi(nom_complet, longueur_max=255, erreur=NomInvalide, sujet="nom")

    utilisateur = User(email=normalisee, full_name=nom, state="onboarding")
    try:
        # SAVEPOINT : seul l'INSERT est annulé en cas de course, pas toute la
        # transaction extérieure (contrairement à un `session.rollback()`).
        async with session.begin_nested():
            session.add(utilisateur)
            await session.flush()
    except IntegrityError:
        # Course : une requête concurrente a créé le compte entre notre SELECT
        # et notre INSERT. Fréquent quand l'utilisateur tape deux fois sur
        # « Valider » sur une connexion instable (§11). `email` est désormais la
        # SEULE contrainte d'unicité de la table : si `deja` reste introuvable,
        # la cause est autre et inconnue, on laisse l'IntegrityError remonter
        # plutôt que de la traduire en une erreur métier qui mentirait.
        deja = await par_adresse(session, normalisee)
        if deja is not None:
            return deja
        raise
    return utilisateur


async def revoquer_jetons(session: AsyncSession, utilisateur: User) -> None:
    """Invalide d'un coup tous les jetons émis pour ce compte (§5)."""
    utilisateur.token_version += 1
    await session.flush()
```

- [ ] **Step 4 : supprimer le module de normalisation et son test**

```bash
git rm src/core/telephone.py tests/test_telephone.py
```

Puis retirer la ligne `    "phonenumbers>=8.13",` de `pyproject.toml`.

- [ ] **Step 5 : retirer les quatre exceptions**

Dans `src/core/erreurs.py` :
- supprimer de `__all__` : `"NumeroInvalide",`, `"TelephoneDejaUtilise",`, `"ContactUsurpe",`, `"TelegramDejaLie",` ;
- supprimer les classes `NumeroInvalide` (l. 36-37), `TelephoneDejaUtilise` (l. 82-83), `ContactUsurpe` (l. 86-89), `TelegramDejaLie` (l. 100-103) ;
- corriger la docstring du module, qui renvoie à `src/bot/texts.py` :

```python
"""Exceptions métier, traduites par chaque client (CLAUDE.md §4).

Chacune porte un `code` stable. L'API le renvoie tel quel, le client web le
traduit via ses propres libellés. Aucun texte destiné à un utilisateur ne doit
apparaître ici.
"""
```

- corriger la docstring de `InscriptionIncomplete`, qui mentionne le téléphone :

```python
class InscriptionIncomplete(ErreurMetier):
    """Code valide, mais le compte est nouveau et le nom manque."""

    code = "inscription_incomplete"
```

- [ ] **Step 6 : retirer les quatre traductions HTTP**

Dans `src/api/app.py`, supprimer de l'import `NumeroInvalide,`, `TelegramDejaLie,`, `TelephoneDejaUtilise,` et `ContactUsurpe,` (ce dernier est importé plus haut dans la liste), puis les quatre lignes correspondantes de `_STATUTS` :

```python
    NumeroInvalide: status.HTTP_422_UNPROCESSABLE_CONTENT,
    TelephoneDejaUtilise: status.HTTP_409_CONFLICT,
    TelegramDejaLie: status.HTTP_409_CONFLICT,
    ContactUsurpe: status.HTTP_400_BAD_REQUEST,
```

- [ ] **Step 7 : corriger les deux commentaires périmés de `auth.py`**

Dans `src/api/routers/auth.py`, aux alentours de la ligne 195, le commentaire explique que `NumeroInvalide` et `TelephoneDejaUtilise` ne peuvent plus remonter de cet endpoint et renvoie vers `comptes.definir_telephone`. Ces trois noms n'existent plus. Le remplacer par :

```python
        # Aucun téléphone ici : depuis le 2026-09-12 l'identité d'un compte est
        # son adresse email et rien d'autre (migration 0005). Le numéro
        # réapparaîtra en Phase 3 dans le profil, extrait du CV.
```

Vérifier d'abord le contexte exact avec `sed -n '185,210p' src/api/routers/auth.py` : ne remplacer que les lignes de commentaire, aucune ligne de code.

- [ ] **Step 8 : adapter `tests/test_auth_comptes.py`**

Supprimer les tests devenus sans objet : `test_inscription_sans_telephone_reussit`, `test_deux_comptes_sans_telephone_coexistent`, `test_definir_telephone_pose_le_numero`, `test_definir_telephone_deja_utilise_par_un_autre_compte`, `test_definir_telephone_reste_idempotent_sur_le_meme_compte`, `test_definir_telephone_numero_invalide_refuse`, `test_liaison_telegram_attache_l_utilisateur_fourni`, celui de l'idempotence de la liaison, et `test_liaison_telegram_deja_rattache_a_un_autre_compte`.

Retirer de l'import `NumeroInvalide,`, `TelegramDejaLie,`, `TelephoneDejaUtilise,`, ainsi que la constante `TEL` si elle devient inutilisée. Dans le test qui subsiste et qui asserte `u.telegram_id is None` (l. 56), supprimer cette seule assertion. Réécrire la docstring de tête :

```python
"""Comptes : inscription et reconnexion par adresse email (spec Phase 2 §8).

Depuis le 2026-09-12, l'identité d'un compte est son adresse email et rien
d'autre : `users.phone` et `users.telegram_id` ont été supprimées (migration
0005).
"""
```

- [ ] **Step 9 : lancer la suite complète**

Run: `.venv/bin/python -m pytest -q && RUN_INTEGRATION_TESTS=1 .venv/bin/python -m pytest -m integration -q`
Expected: tout vert. Certains tests d'intégration écrivent encore `User(..., phone=...)` — ils ne casseront qu'à la Tâche 4, quand la colonne partira du modèle. S'ils échouent DÈS MAINTENANT, c'est un vrai problème : s'arrêter et diagnostiquer.

- [ ] **Step 10 : vérifier ruff et mypy**

Run: `.venv/bin/python -m ruff check src/ tests/ && .venv/bin/python -m mypy src/`
Expected: `All checks passed` et `Success`.

- [ ] **Step 11 : commit**

```bash
git add -A
git commit -m "$(cat <<'MSG'
feat(core): retirer le téléphone et telegram_id de la couche métier

comptes.py perd par_telephone, par_telegram, lier_telegram et
definir_telephone ; erreurs.py perd NumeroInvalide, TelephoneDejaUtilise,
ContactUsurpe et TelegramDejaLie, avec leurs quatre traductions HTTP.
src/core/telephone.py et la dépendance phonenumbers disparaissent.

L'identité d'un compte est son adresse email, et rien d'autre. Le numéro
réapparaîtra en Phase 3 dans profiles.structured, extrait du CV, sans
contrainte d'unicité ni prétention de vérification.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Sep8DxRJusdAs9r2zWaZCk
MSG
)"
```

---

## Task 4 : migration 0005, modèle et sortie de `/moi`

**Files:**
- Create: `alembic/versions/0005_retrait_telephone_telegram.py`
- Modify: `src/db/models.py:69-80`, `src/api/schemas/auth.py`, `tests/test_identite_migration.py`, `tests/test_migrations.py`, `tests/test_logs_sans_pii.py`, `tests/test_api_auth_verifie.py`, `tests/test_api_moi.py`
- Test: `tests/test_identite_migration.py`, `tests/test_api_auth_verifie.py`

**Interfaces:**
- Consomme : `src.core.auth.comptes` sans les fonctions retirées (Tâche 3).
- Produit : `User` sans `phone` ni `telegram_id`. `Utilisateur` (schéma de sortie) expose exactement `id`, `email`, `nom_complet`, `etat`. Révision alembic de tête : `a1c2e3f40005`.

- [ ] **Step 1 : écrire les tests qui échouent**

Dans `tests/test_identite_migration.py`, remplacer les assertions de nullabilité (l. 26-27 et 59-60) et les tests qui posent un `phone` par :

```python
@pytest.mark.integration
async def test_les_colonnes_telephone_et_telegram_ont_disparu(session: AsyncSession) -> None:
    """Migration 0005 : `users` n'a plus que l'adresse email comme identité."""
    etat = dict(
        (
            await session.execute(
                text(
                    "SELECT column_name, is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'users'"
                )
            )
        ).all()
    )
    assert "phone" not in etat
    assert "telegram_id" not in etat
    assert etat["email"] == "NO"


@pytest.mark.integration
async def test_le_modele_n_expose_plus_ces_champs() -> None:
    from src.db.models import User

    assert not hasattr(User, "phone")
    assert not hasattr(User, "telegram_id")
```

Supprimer `test_compte_sans_telegram_accepte`, `test_deux_comptes_sans_telegram_acceptes`, `test_compte_sans_telephone_accepte`, `test_deux_comptes_sans_telephone_coexistent` et `test_telephone_en_double_refuse`. Conserver le test du doublon d'email en retirant l'argument `phone=` de ses deux `User(...)`.

Dans `tests/test_api_auth_verifie.py`, remplacer les assertions `corps["telephone"] is None` (l. 58, 83, 160, 168, 184) et `corps["telegram_lie"] is False` (l. 59) par une assertion de forme, une seule fois, dans le test d'inscription nominal :

```python
    assert set(corps) == {"id", "email", "nom_complet", "etat"}
```

- [ ] **Step 2 : lancer les tests pour vérifier qu'ils échouent**

Run: `RUN_INTEGRATION_TESTS=1 .venv/bin/python -m pytest -m integration tests/test_identite_migration.py -v`

**`-m integration` est obligatoire**, et pas seulement la variable d'environnement : `pyproject.toml` porte `addopts = "-m 'not integration'"`, qui dé-sélectionne ces tests par défaut. Sans le marqueur explicite, la commande ne collecte RIEN et paraît réussir — défaut rencontré pour de vrai en Tâche 2.
Expected: `test_les_colonnes_telephone_et_telegram_ont_disparu` ÉCHOUE (`phone` est encore là), `test_le_modele_n_expose_plus_ces_champs` ÉCHOUE.

- [ ] **Step 3 : écrire la migration 0005**

Créer `alembic/versions/0005_retrait_telephone_telegram.py` :

```python
"""retrait du téléphone et de telegram_id

Décision du porteur du projet le 2026-09-12 : Telegram cesse d'être un client
du produit, et le numéro de téléphone quitte la table d'identité.

`phone` était UNIQUE : tant que la colonne existait avec cette contrainte, un
tiers pouvait réserver le numéro d'autrui sur son propre compte et l'empêcher
de le saisir sur le sien. La rendre facultative (migration 0004) avait réduit
le trou sans le fermer. Le supprimer le ferme.

`telegram_id` part avec le client Telegram : plus de bot, plus d'identifiant
Telegram à rattacher.

L'identité d'un compte est désormais son adresse email, et rien d'autre. Le
numéro réapparaîtra en Phase 3 dans `profiles.structured`, extrait du CV, sans
contrainte d'unicité ni prétention de vérification.

PostgreSQL supprime avec une colonne les index qui la portent : il n'y a pas
d'index à défaire séparément.

Le `downgrade` recrée les deux colonnes nullables avec leurs index uniques,
mais **ne restaure aucune donnée** : il rend le schéma, pas le contenu. C'est
acceptable ici, la base ne portait aucun utilisateur au moment du retrait.

Revision ID: a1c2e3f40005
Revises: a1c2e3f40004
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1c2e3f40005"
down_revision: str | None = "a1c2e3f40004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("users", "phone")
    op.drop_column("users", "telegram_id")


def downgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("telegram_id", sa.BigInteger(), nullable=True))
    op.create_index(op.f("ix_users_phone"), "users", ["phone"], unique=True)
    op.create_index(op.f("ix_users_telegram_id"), "users", ["telegram_id"], unique=True)
```

**Avant d'écrire les noms d'index du `downgrade`, les relever dans la base** :

```bash
docker exec jobbot-postgres-1 psql -U jobbot -d jobbot -c "\d users"
```

Reprendre les noms exacts affichés, sans les deviner.

- [ ] **Step 4 : retirer les deux colonnes du modèle**

Dans `src/db/models.py`, supprimer les lignes 70-80 (les deux `mapped_column` et leurs commentaires) et les remplacer par :

```python
    # Identité de connexion, et la seule, depuis le 2026-09-12 (CLAUDE.md §5).
    # Avant le 2026-09-11 c'était `telegram_id` ; `phone` a été retiré par la
    # migration 0005 (un numéro saisi au clavier n'est prouvé par rien, et sa
    # contrainte d'unicité permettait de réserver celui d'autrui).
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
```

Vérifier ensuite que `BigInteger` est encore utilisé ailleurs dans le fichier (`jobs`, `usage_counters`) : s'il ne l'est plus, retirer l'import, sinon ruff le signalera.

- [ ] **Step 5 : réduire le schéma de sortie**

Dans `src/api/schemas/auth.py`, remplacer la classe `Utilisateur` par :

```python
class Utilisateur(BaseModel):
    """Ce qu'un client a le droit de savoir d'un compte.

    Volontairement restreint : `token_version` et les identifiants internes
    n'ont aucune raison de sortir.
    """

    id: int
    email: str
    nom_complet: str | None
    etat: str

    @classmethod
    def depuis(cls, utilisateur: Any) -> Utilisateur:
        """Projette une ligne `users`. Ici plutôt que dans un router : deux
        routers en ont besoin, et importer une fonction privée d'un router
        depuis un autre recouplerait les deux."""
        return cls(
            id=utilisateur.id,
            email=utilisateur.email,
            nom_complet=utilisateur.full_name,
            etat=utilisateur.state,
        )
```

- [ ] **Step 6 : appliquer la migration sur la base de développement**

```bash
docker exec jobbot-postgres-1 psql -U jobbot -d jobbot -c "select count(*) as offres from jobs; select count(*) as users from users;"
```

Noter les deux nombres (attendu : 232 et 0). Puis, **depuis le dépôt principal** (`/home/mamadbah/projects/jobbot`, seul endroit où `.env` existe) :

```bash
docker compose run --rm migrate
```

Puis revenir dans le worktree et vérifier :

```bash
docker exec jobbot-postgres-1 psql -U jobbot -d jobbot -c "select * from alembic_version;" -c "\d users" -c "select count(*) from jobs;"
```

Expected: `a1c2e3f40005`, plus de colonnes `phone` ni `telegram_id`, et **232 offres toujours là**. Si le compte d'offres a changé, s'arrêter immédiatement.

- [ ] **Step 7 : adapter les tests qui écrivaient ces colonnes**

Dans `tests/test_migrations.py` (l. 72-84) : retirer `phone` et `telegram_id` des deux `INSERT INTO users`, et leurs valeurs du dictionnaire de paramètres.

Dans `tests/test_logs_sans_pii.py` : retirer `"telephone": TEL,` du corps envoyé à `/auth/code/verifie` (l. 96). **Conserver** les trois assertions `TEL not in rendu` et leurs variantes : elles prouvent désormais qu'un numéro envoyé par un client — même s'il est ignoré — ne ressort pas dans les logs. Ajouter le numéro au corps de la requête en tant que champ inconnu pour que l'assertion garde un sens :

```python
        json={
            "email": ADRESSE,
            "code": code,
            "nom_complet": "Fatou Diop",
            # Champ inconnu du schéma, volontairement : la preuve porte sur le
            # fait qu'un numéro transmis par un client ne ressort NULLE PART
            # dans les logs, même rejeté (§2, interdiction n°2).
            "telephone": TEL,
        },
```

Dans `tests/test_api_moi.py` : retirer toute assertion portant sur `telephone` ou `telegram_lie` dans la réponse de `/moi`.

- [ ] **Step 8 : lancer la suite complète**

Run: `.venv/bin/python -m pytest -q && RUN_INTEGRATION_TESTS=1 .venv/bin/python -m pytest -m integration -q`
Expected: tout vert, zéro avertissement.

- [ ] **Step 9 : vérifier ruff et mypy**

Run: `.venv/bin/python -m ruff check src/ tests/ && .venv/bin/python -m mypy src/`
Expected: `All checks passed` et `Success`.

- [ ] **Step 10 : commit**

```bash
git add -A
git commit -m "$(cat <<'MSG'
feat(db): supprimer users.phone et users.telegram_id (migration 0005)

L'identité d'un compte est son adresse email, et rien d'autre.

phone était UNIQUE : tant que la colonne existait avec cette contrainte,
un tiers pouvait réserver le numéro d'autrui et l'empêcher de le saisir
sur son propre compte. La migration 0004 avait réduit le trou en rendant
la colonne facultative ; la supprimer le ferme.

La réponse de /moi tombe à quatre champs : id, email, nom_complet, etat.

232 offres vérifiées intactes avant et après la migration.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Sep8DxRJusdAs9r2zWaZCk
MSG
)"
```

---

## Task 5 : canal d'alerte administrateur par email

**Files:**
- Modify: `src/courriel/provider.py`, `src/courriel/console.py`, `src/alerting.py` (réécriture complète), `src/core/alerte.py:1-8` (docstring), `src/config.py` (ajout `admin_courriel`, retrait `admin_telegram_id`), `.env.example`, `README.md`
- Test: `tests/test_alerting.py` (réécriture complète), `tests/conftest.py:110-125`

**Interfaces:**
- Consomme : `FournisseurCourriel` de `src/courriel/provider.py`, `construire_fournisseur(settings)`.
- Produit : `FournisseurCourriel` gagne `envoyer_message(destinataire: str, sujet: str, corps: str) -> None`. `src/alerting.py` expose `AlerteJournalisee()` (plus d'argument), `AlerteCourriel(destinataire: str, fournisseur: FournisseurCourriel)` et `construire_alerte(settings) -> AlerteAdmin`. `Settings` gagne `admin_courriel: str = ""`.

- [ ] **Step 1 : écrire les tests qui échouent**

Remplacer tout `tests/test_alerting.py` par :

```python
"""Alerte administrateur (CLAUDE.md §7 : « ne jamais échouer en silence »).

Telegram portait ce canal jusqu'au 2026-09-12. Il passe à l'email, derrière le
même protocole `AlerteAdmin` : aucun appelant ne change.
"""

from __future__ import annotations

import pytest
from structlog.testing import capture_logs

from src.alerting import AlerteCourriel, AlerteJournalisee, construire_alerte
from src.config import get_settings


class FournisseurEspion:
    """Capture les messages, n'envoie rien."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str]] = []

    async def envoyer_code(self, destinataire: str, code: str) -> None:  # pragma: no cover
        raise AssertionError("une alerte ne doit jamais passer par envoyer_code")

    async def envoyer_message(self, destinataire: str, sujet: str, corps: str) -> None:
        self.messages.append((destinataire, sujet, corps))


class FournisseurEnPanne:
    async def envoyer_code(self, destinataire: str, code: str) -> None:  # pragma: no cover
        raise AssertionError("non sollicité")

    async def envoyer_message(self, destinataire: str, sujet: str, corps: str) -> None:
        raise RuntimeError("smtp injoignable")


async def test_journalise_l_alerte_en_erreur() -> None:
    with capture_logs() as journal:
        await AlerteJournalisee().envoyer("scraper_casse", source="x")
    (evenement,) = journal
    assert evenement["log_level"] == "error"
    assert evenement["alerte"] == "scraper_casse"
    assert evenement["source"] == "x"
    assert evenement["canal"] == "log_uniquement_admin_non_configure"


async def test_l_alerte_courriel_part_par_le_fournisseur() -> None:
    espion = FournisseurEspion()
    with capture_logs() as journal:
        await AlerteCourriel("admin@jobbot.sn", espion).envoyer(
            "scraper_casse", source="emploidakar", offres=0
        )
    (destinataire, sujet, corps) = espion.messages[0]
    assert destinataire == "admin@jobbot.sn"
    assert "scraper_casse" in sujet
    assert "emploidakar" in corps
    assert "offres : 0" in corps
    # L'alerte reste tracée dans les logs du VPS même quand elle part par email :
    # le fichier de logs est le seul historique consultable après coup.
    assert journal[0]["alerte"] == "scraper_casse"
    assert journal[0]["canal"] == "courriel"


async def test_une_panne_d_envoi_ne_remonte_pas_a_l_appelant() -> None:
    """L'appelant est au milieu d'un chemin d'erreur : il ne peut rien faire de
    cette exception, et une alerte qui explose en signalant un incident
    aggrave l'incident."""
    with capture_logs() as journal:
        await AlerteCourriel("admin@jobbot.sn", FournisseurEnPanne()).envoyer("scraper_casse")
    evenements = [e["event"] for e in journal]
    assert "alerte_admin" in evenements
    assert "alerte_admin_envoi_echoue" in evenements


def test_la_fabrique_choisit_le_courriel_quand_une_adresse_est_configuree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ADMIN_COURRIEL", "admin@jobbot.sn")
    get_settings.cache_clear()
    alerte = construire_alerte(get_settings())
    assert isinstance(alerte, AlerteCourriel)
    assert alerte.destinataire == "admin@jobbot.sn"


def test_la_fabrique_retombe_sur_le_log_sans_adresse() -> None:
    """Sans destinataire, on ne peut que journaliser — et le dire dans
    l'événement, pour ne pas croire l'alerte transmise."""
    get_settings.cache_clear()
    assert get_settings().admin_courriel == ""
    assert isinstance(construire_alerte(get_settings()), AlerteJournalisee)


def test_le_reglage_telegram_de_l_admin_n_existe_plus() -> None:
    from src.config import Settings

    assert "admin_telegram_id" not in Settings.model_fields

```

- [ ] **Step 2 : lancer les tests pour vérifier qu'ils échouent**

Run: `.venv/bin/python -m pytest tests/test_alerting.py -v`
Expected: ÉCHEC à l'import — `AlerteCourriel` n'existe pas dans `src.alerting`.

- [ ] **Step 3 : ajouter `envoyer_message` au protocole d'envoi**

Dans `src/courriel/provider.py`, ajouter la méthode au `Protocol` :

```python
class FournisseurCourriel(Protocol):
    """Canal d'envoi vers une adresse email."""

    async def envoyer_code(self, destinataire: str, code: str) -> None:
        """Transmet le code de vérification à l'adresse indiquée."""
        ...

    async def envoyer_message(self, destinataire: str, sujet: str, corps: str) -> None:
        """Transmet un message quelconque. Sert aux alertes d'exploitation
        (`src/alerting.py`), jamais à un recruteur : le service n'écrit à
        personne d'autre que ses propres utilisateurs et son administrateur
        (CLAUDE.md §2, interdiction n°1, et §7)."""
        ...
```

- [ ] **Step 4 : implémenter `envoyer_message` dans le fournisseur console**

Dans `src/courriel/console.py`, ajouter à `CourrielConsole` :

```python
    async def envoyer_message(self, destinataire: str, sujet: str, corps: str) -> None:
        log.warning(
            "message_non_envoye_mode_console",
            destinataire=destinataire,
            sujet=sujet,
            corps=corps,
        )
```

- [ ] **Step 5 : réécrire `src/alerting.py`**

```python
"""Alertes administrateur (CLAUDE.md §7, §12 Phase 8).

« Ne jamais échouer en silence » : un scraper cassé, une source bloquée ou un
changement de structure doivent sortir du fichier de logs et arriver à
quelqu'un.

Le canal était Telegram jusqu'au 2026-09-12. Il passe à l'email, derrière le
même protocole `AlerteAdmin` : ni `src/core/auth/limites.py` ni le worker
d'ingestion ne changent d'une ligne. Le bac à sable d'un fournisseur
transactionnel sait envoyer vers l'adresse vérifiée du propriétaire du compte
sans domaine possédé, donc ce canal est exploitable avant que le §14.1 soit
tranché — contrairement aux emails vers de vrais utilisateurs.

Sans `ADMIN_COURRIEL`, on retombe sur le log : c'est un état dégradé mais
fonctionnel, et l'événement le dit explicitement pour qu'on ne croie pas
l'alerte transmise.
"""

from __future__ import annotations

from typing import Any

from src.config import Settings
from src.core.alerte import AlerteAdmin
from src.courriel.provider import FournisseurCourriel, construire_fournisseur
from src.logging_setup import get_logger

log = get_logger(__name__)

__all__ = ["AlerteAdmin", "AlerteCourriel", "AlerteJournalisee", "construire_alerte"]


def _corps(contexte: dict[str, Any]) -> str:
    """Contexte en texte lisible, une clé par ligne, ordre stable."""
    if not contexte:
        return "(aucun contexte)"
    return "\n".join(f"{cle} : {valeur}" for cle, valeur in sorted(contexte.items()))


class AlerteJournalisee:
    """Alerte écrite dans les logs en niveau ERROR.

    Repli permanent quand aucun destinataire n'est configuré.
    """

    async def envoyer(self, evenement: str, **contexte: Any) -> None:
        log.error(
            "alerte_admin",
            alerte=evenement,
            destinataire="absent",
            canal="log_uniquement_admin_non_configure",
            **contexte,
        )


class AlerteCourriel:
    """Alerte envoyée par email, et journalisée dans tous les cas.

    Le log part AVANT la tentative d'envoi : une alerte doit rester traçable
    dans les logs du VPS même si l'envoi échoue, et c'est le seul historique
    consultable après coup.
    """

    def __init__(self, destinataire: str, fournisseur: FournisseurCourriel) -> None:
        self.destinataire = destinataire
        self.fournisseur = fournisseur

    async def envoyer(self, evenement: str, **contexte: Any) -> None:
        log.error(
            "alerte_admin",
            alerte=evenement,
            destinataire=self.destinataire,
            canal="courriel",
            **contexte,
        )
        try:
            await self.fournisseur.envoyer_message(
                self.destinataire, f"[JobBot] {evenement}", _corps(contexte)
            )
        except Exception as exc:
            # Volontairement large : l'appelant est au milieu d'un chemin
            # d'erreur (plafond atteint, scraper cassé) et ne peut rien faire
            # de cette exception. Une alerte qui explose en signalant un
            # incident aggrave l'incident. Le log ci-dessus est déjà parti.
            log.error("alerte_admin_envoi_echoue", alerte=evenement, erreur=str(exc))


def construire_alerte(settings: Settings) -> AlerteAdmin:
    """Canal d'alerte à utiliser, selon la configuration."""
    if not settings.admin_courriel:
        return AlerteJournalisee()
    return AlerteCourriel(settings.admin_courriel, construire_fournisseur(settings))
```

- [ ] **Step 6 : corriger la docstring du protocole `AlerteAdmin`**

Dans `src/core/alerte.py`, remplacer `l'alerte part (log, Telegram...)` par `l'alerte part (log, email...)`. Ne toucher à rien d'autre : la signature du protocole ne change pas.

- [ ] **Step 7 : remplacer le réglage dans la configuration**

Dans `src/config.py`, supprimer la ligne `    admin_telegram_id: int = 0` et ajouter, dans la section Authentification (à côté de `fournisseur_courriel`) :

```python
    # Destinataire des alertes d'exploitation (scraper cassé, plafond global
    # atteint, coût LLM). Vide = alertes journalisées seulement : un état
    # dégradé mais fonctionnel, contrairement à FOURNISSEUR_COURRIEL=console
    # qui est un trou de sécurité et fait échouer le démarrage en prod.
    admin_courriel: str = ""
```

Dans `.env.example`, remplacer les deux lignes `ADMIN_TELEGRAM_ID` par, dans la section de l'authentification :

```
# Destinataire des alertes techniques (scraper cassé, plafond atteint).
# Vide = alertes en logs uniquement.
ADMIN_COURRIEL=
```

Dans `README.md`, ajouter une ligne au tableau de la liste de contrôle avant mise en production :

```
| `ADMIN_COURRIEL` | Sans lui, une alerte de scraper cassé ne part nulle part : elle reste dans les logs du VPS, à lire à la main |
```

- [ ] **Step 8 : aligner le fournisseur espion des tests**

Dans `tests/conftest.py`, ajouter à `FournisseurCourrielEspion` :

```python
    async def envoyer_message(self, destinataire: str, sujet: str, corps: str) -> None:
        self.messages.append((destinataire, sujet, corps))
```

et initialiser `self.messages: list[tuple[str, str, str]] = []` dans son `__init__`.

- [ ] **Step 9 : lancer la suite complète**

Run: `.venv/bin/python -m pytest -q && RUN_INTEGRATION_TESTS=1 .venv/bin/python -m pytest -m integration -q`
Expected: tout vert. `AlerteJournalisee(` n'est construit nulle part ailleurs que dans `tests/test_alerting.py`, que ce Step 1 réécrit entièrement — vérifié avant l'écriture de ce plan, il n'y a pas d'autre site d'appel à corriger.

- [ ] **Step 10 : vérifier ruff et mypy**

Run: `.venv/bin/python -m ruff check src/ tests/ && .venv/bin/python -m mypy src/`
Expected: `All checks passed` et `Success`.

- [ ] **Step 11 : commit**

```bash
git add -A
git commit -m "$(cat <<'MSG'
feat(alerting): alertes administrateur par email

Telegram portait le seul canal d'alerte prévu (§7 : « ne jamais échouer
en silence »). Il passe à l'email, derrière le protocole AlerteAdmin
existant : ni limites.py ni le worker d'ingestion ne changent d'une ligne.

Le log part AVANT la tentative d'envoi, et une panne du fournisseur ne
remonte pas à l'appelant : celui-ci est au milieu d'un chemin d'erreur et
une alerte qui explose en signalant un incident aggrave l'incident.

Sans ADMIN_COURRIEL, on retombe sur le log et l'événement le dit. C'est
un état dégradé mais fonctionnel, contrairement à FOURNISSEUR_COURRIEL=
console qui est un trou de sécurité et fait échouer le démarrage en prod.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Sep8DxRJusdAs9r2zWaZCk
MSG
)"
```

---

## Task 6 : nettoyer la configuration Telegram

**Files:**
- Modify: `src/config.py:16-17,34-42`, `.env.example:1-19`, `tests/conftest.py:28-32`, `tests/test_config.py:11-15`, `tests/test_worker_ingest.py:210,224`, `tests/test_sante_scraper.py:4`, `tests/test_retrait_telegram_telephone.py`
- Test: `tests/test_config.py`, `tests/test_retrait_telegram_telephone.py`

**Interfaces:**
- Consomme : `admin_courriel` présent et `admin_telegram_id` absent (Tâche 5).
- Produit : `Settings()` se construit sans aucune variable d'environnement. Aucun champ de `Settings` ne commence par `telegram_`.

- [ ] **Step 1 : écrire les tests qui échouent**

Dans `tests/test_config.py`, remplacer `test_token_obligatoire` par son inverse :

```python
def test_aucune_valeur_n_est_obligatoire(monkeypatch: pytest.MonkeyPatch) -> None:
    """`TELEGRAM_BOT_TOKEN` était la seule valeur obligatoire du projet, et
    l'était pour TOUS les processus : l'API et les workers refusaient de
    démarrer sans elle. Depuis son retrait, `.env.example` se copie et la pile
    démarre sans qu'une seule valeur soit renseignée — c'est le critère de
    validation de la Phase 0 (CLAUDE.md §12), désormais vrai sans réserve."""
    # Seuls les noms que `Settings` lit, et pas toutes les variables en
    # majuscules : effacer PATH, HOME ou LANG le temps d'un test est
    # gratuitement dangereux, même si monkeypatch les restaure ensuite.
    for champ in Settings.model_fields:
        monkeypatch.delenv(champ.upper(), raising=False)
    get_settings.cache_clear()
    reglages = Settings()  # type: ignore[call-arg]
    assert reglages.environment == "dev"
```

Aucun import supplémentaire : `Settings` et `get_settings` sont déjà importés par ce fichier.

Ajouter à `tests/test_retrait_telegram_telephone.py` :

```python
def test_aucun_reglage_telegram_ne_subsiste() -> None:
    from src.config import Settings

    restants = [nom for nom in Settings.model_fields if "telegram" in nom]
    assert not restants, f"réglages Telegram encore déclarés : {restants}"


def test_aucune_variable_telegram_dans_l_exemple_d_environnement() -> None:
    """`.env.example` est public (le dépôt est public) et sert de référence de
    déploiement : une variable morte y ferait croire qu'il faut la renseigner."""
    contenu = Path(".env.example").read_text(encoding="utf-8")
    assert "TELEGRAM" not in contenu.upper()
```

- [ ] **Step 2 : lancer les tests pour vérifier qu'ils échouent**

Run: `.venv/bin/python -m pytest tests/test_config.py::test_aucune_valeur_n_est_obligatoire tests/test_retrait_telegram_telephone.py -v`
Expected: `test_aucune_valeur_n_est_obligatoire` ÉCHOUE sur une `ValidationError` (`telegram_bot_token` manquant), les deux gardes ÉCHOUENT.

- [ ] **Step 3 : retirer les réglages Telegram**

Dans `src/config.py` : supprimer la ligne 17 `TelegramMode = Literal["polling", "webhook"]` et le bloc complet des lignes 34-42 (`# --- Telegram ---` jusqu'à `admin_telegram_id`, déjà retirée en Tâche 5). Vérifier que `Literal` reste importé : `Environment` l'utilise encore.

- [ ] **Step 4 : nettoyer `.env.example`**

Remplacer l'en-tête et la section Telegram (lignes 1-19) par :

```
# ─────────────────────────────────────────────────────────────
# JobBot Sénégal — copier en .env. Aucune valeur n'est obligatoire
# en développement : tout a un défaut fonctionnel en local.
# Voir README.md pour ce qu'il faut poser avant la production.
# ─────────────────────────────────────────────────────────────

# --- Général ---
ENVIRONMENT=dev
LOG_LEVEL=INFO
```

- [ ] **Step 5 : retirer le token de l'environnement des tests**

Dans `tests/conftest.py`, réduire `_ENV_MINIMAL` :

```python
_ENV_MINIMAL = {
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PASSWORD": "motdepasse_test",
}
```

Dans `tests/test_worker_ingest.py`, remplacer les deux occurrences (l. 210 et 224) :

```python
    settings = Settings()  # type: ignore[call-arg]
```

- [ ] **Step 6 : corriger la docstring de `test_sante_scraper.py`**

Ligne 4, remplacer `log ERROR + notification Telegram à l'admin` par `log ERROR + alerte email à l'admin`.

- [ ] **Step 7 : lancer la suite complète**

Run: `.venv/bin/python -m pytest -q && RUN_INTEGRATION_TESTS=1 .venv/bin/python -m pytest -m integration -q`
Expected: tout vert, zéro avertissement.

- [ ] **Step 8 : vérifier qu'aucune trace de Telegram ne subsiste dans le code**

Run: `grep -rn -i "telegram\|aiogram" src/ tests/ alembic/ docker-compose.yml .env.example pyproject.toml`
Expected: **uniquement** des mentions historiques assumées — les docstrings de migrations (`0001`, `0002`, `0004`, `0005`) qui racontent pourquoi le schéma a changé, et le nom des gardes dans `tests/test_retrait_telegram_telephone.py`. Aucune ligne de code exécutable. Toute autre occurrence est un oubli : la traiter avant de commiter.

- [ ] **Step 9 : vérifier ruff et mypy**

Run: `.venv/bin/python -m ruff check src/ tests/ && .venv/bin/python -m mypy src/`
Expected: `All checks passed` et `Success`.

- [ ] **Step 10 : commit**

```bash
git add -A
git commit -m "$(cat <<'MSG'
chore(config): retirer les réglages Telegram

TELEGRAM_BOT_TOKEN était la seule valeur obligatoire du projet, et
l'était pour TOUS les processus : l'API et les workers refusaient de
démarrer sans elle, alors qu'aucun des deux ne parlait à Telegram.

.env.example se copie désormais tel quel et la pile démarre sans qu'une
seule valeur soit renseignée. Le critère de validation de la Phase 0
(« fonctionne sur une machine vierge à partir du seul .env.example »)
devient vrai sans réserve.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Sep8DxRJusdAs9r2zWaZCk
MSG
)"
```

---

## Task 7 : réécrire le brief, le README et la spec de la Phase 2

**Files:**
- Modify: `CLAUDE.md` (douze sections), `README.md`, `docs/superpowers/specs/2026-09-11-socle-backend-design.md`

**Interfaces:**
- Consomme : l'état du code à la fin de la Tâche 6.
- Produit : un brief qui ne décrit plus rien d'inexistant.

- [ ] **Step 1 : réécrire les douze sections du CLAUDE.md**

Le §7 de la spec (`docs/superpowers/specs/2026-09-12-retrait-telegram-design.md`) porte le tableau exact des modifications attendues. Les appliquer une par une :

| § | Ce qu'il faut changer |
|---|---|
| §1 | Le produit est accessible par une application web (PWA). Retirer la phrase sur le bot comme client de plein droit. |
| §2 | La ligne « Premier client = web ; Telegram remis à niveau ensuite » devient « Client unique = **web (Next.js, PWA)** — Figé le 2026-09-12 ». La ligne d'authentification perd toute mention de téléphone. |
| §3 | Retirer la ligne `Bot aiogram 3.x (async)` du bloc de stack, et les entrées `aiogram` et `phonenumbers` des deux tableaux de dépendances. |
| §4 | Quatre processus (`api`, `web`, `worker_ingest`, `worker_match`). Retirer la phrase « Le bot n'appelle pas l'API par HTTP » **en conservant la règle qu'elle servait** : `src/core/` reste la seule copie de la règle métier et son test d'isolation demeure. Retirer de l'arborescence `src/bot/`, `src/core/telephone.py` et `/moi/telegram/jeton`. Ajouter `tests/test_retrait_telegram_telephone.py` n'est pas nécessaire : l'arborescence du §4 ne détaille pas `tests/`. |
| §5 | `users` perd `phone` et `telegram_id`. Remplacer l'encadré « Pourquoi `phone` est devenu facultatif » par une note courte : la colonne est supprimée, son unicité permettait de réserver le numéro d'autrui, et le numéro réapparaîtra en Phase 3 dans `profiles.structured`. |
| §6 | Onboarding étape 1 : « Adresse email → code à 6 chiffres → nom ». Supprimer tout le paragraphe sur « partager mon contact » et le garde-fou `contact.user_id == message.from_user.id`. |
| §7 | L'alerte de scraper cassé part **par email** à l'admin. La livraison du dossier (Phase 5) se fait par téléchargement depuis le web. |
| §10 | Le repli manuel `/paiement_manuel` devient une page web ; l'activation se fait par commande CLI. Le webhook reste servi par `api`. |
| §11 | Retirer `/aide` côté Telegram, garder son équivalent web. Le comptage des abandons d'onboarding ne concerne plus que le web. |
| §12 | **Supprimer la Phase 7.** Réécrire les critères de validation de la Phase 2 avec les quatre du §8 de la spec. Phase 8 : remplacer « commandes Telegram suffisent » par les commandes CLI sur le VPS. |
| §14 | Ajouter le canal d'administration comme tranché-non-fait (alertes email + CLI). Retirer le téléphone de la liste des données stockées au point 7. |
| §15 | Supprimer la note sur le FAI qui bloque `api.telegram.org` : sans bot, elle n'a plus d'objet. |

- [ ] **Step 2 : réécrire le parcours du README**

Le parcours de `README.md` (l. 14-40) envoie encore un `"telephone"` à `/auth/code/verifie` et enchaîne sur `/compte` dans Telegram. Le remplacer par :

````markdown
Parcours d'authentification complet, de bout en bout :

```bash
# 1. Demander un code
curl -s -X POST localhost:8080/auth/code/demande \
  -H 'content-type: application/json' -d '{"email":"vous@example.sn"}' -i | head -1

# 2. Lire le code dans les logs (fournisseur console — seul endroit du projet
#    où un code de vérification a le droit d'être journalisé, CLAUDE.md §2)
docker compose logs api --since 1m | grep courriel_non_envoye_mode_console

# 3. S'inscrire avec ce code
curl -s -X POST localhost:8080/auth/code/verifie -c /tmp/cookies.txt \
  -H 'content-type: application/json' \
  -d '{"email":"vous@example.sn","code":"<LE CODE>","nom_complet":"Votre Nom"}'

# 4. Vérifier la session
curl -s localhost:8080/moi -b /tmp/cookies.txt

# 5. Se reconnecter : le MÊME `id` doit revenir, sans doublon
#    (répéter 1 → 3, puis comparer l'`id` rendu par /moi)

# 6. Se déconnecter, puis rejouer le cookie : 401 attendu
curl -s -X POST localhost:8080/auth/deconnexion -b /tmp/cookies.txt -i | head -1
curl -s localhost:8080/moi -b /tmp/cookies.txt -i | head -1
```
````

Corriger aussi la ligne 3 : `Bot Telegram de candidature assistée` → `Candidature assistée`.

- [ ] **Step 3 : corriger la spec de la Phase 2**

Dans `docs/superpowers/specs/2026-09-11-socle-backend-design.md`, §8 : supprimer l'affirmation « on ne crée une ligne `users` qu'après un code valide. Sinon […] `phone UNIQUE` devient un moyen de bloquer le numéro d'autrui. » Elle était **fausse** — elle prétendait fermer un trou qu'elle laissait ouvert. Ne pas la corriger : la supprimer avec la colonne qu'elle décrivait, en laissant une note d'une ligne qui dit que le sujet est traité par la spec du 2026-09-12.

- [ ] **Step 4 : vérifier qu'aucune documentation ne décrit plus Telegram comme actif**

Run: `grep -n -i "telegram" CLAUDE.md README.md | grep -v -i "historique\|avant le\|jusqu'au\|était\|2026-09-0\|2026-09-11"`
Expected: aucune ligne décrivant Telegram au présent. Toute occurrence restante doit être une mention historique explicitement datée.

- [ ] **Step 5 : commit**

```bash
git add -A
git commit -m "$(cat <<'MSG'
docs: retirer Telegram et le téléphone du brief et du README

Douze sections du CLAUDE.md décrivaient un bot, un numéro de téléphone et
une Phase 7 qui n'existent plus. Le parcours du README envoyait encore un
téléphone à /auth/code/verifie et enchaînait sur /compte dans Telegram.

Les critères de validation de la Phase 2 sont réécrits : inscription web
de bout en bout, reconnexion sans doublon, déconnexion qui invalide le
jeton, page d'inscription sous 200 Ko.

La spec du 2026-09-11 portait à son §8 une affirmation fausse sur
phone UNIQUE, écrite en croyant fermer un trou qu'elle laissait ouvert.
Supprimée avec la colonne qu'elle décrivait.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Sep8DxRJusdAs9r2zWaZCk
MSG
)"
```

---

## Task 8 : vérification de bout en bout et mise à jour de la PR #1

**Files:**
- Modify: aucun fichier de code. Cette tâche produit des preuves d'exécution et met à jour la PR.

**Interfaces:**
- Consomme : l'état du dépôt à la fin de la Tâche 7.
- Produit : les quatre critères de validation du §8 de la spec, vérifiés ou explicitement déclarés non vérifiables.

- [ ] **Step 1 : suite complète, unitaire et intégration**

Run:
```bash
.venv/bin/python -m ruff check src/ tests/
.venv/bin/python -m mypy src/
.venv/bin/python -m pytest -q
RUN_INTEGRATION_TESTS=1 .venv/bin/python -m pytest -m integration -q
```
Expected: `All checks passed`, `Success`, et les deux suites vertes avec **zéro avertissement**. Noter les comptes réels — ne pas les recopier depuis ce plan ni depuis un rapport.

- [ ] **Step 2 : vérifier l'intégrité de la base de développement**

Run: `docker exec jobbot-postgres-1 psql -U jobbot -d jobbot -c "select * from alembic_version;" -c "select count(*) from jobs;" -c "\d users"`
Expected: `a1c2e3f40005`, **232 offres**, et une table `users` sans `phone` ni `telegram_id`.

- [ ] **Step 3 : dérouler le parcours réel, depuis le dépôt principal**

Le worktree n'a pas de `.env` : se placer dans `/home/mamadbah/projects/jobbot`, puis :

```bash
git -C /home/mamadbah/projects/jobbot stash list   # vérifier qu'on ne perturbe rien
docker compose up -d --build api
```

**Ne jamais lancer `docker compose down -v`.** Dérouler ensuite les six étapes du README (§Task 7, Step 2) et consigner les résultats :

1. inscription complète : `/auth/code/demande` → code lu dans les logs → `/auth/code/verifie` → `/moi` rend `{id, email, nom_complet, etat}` et rien d'autre ;
2. reconnexion avec la même adresse : **le même `id`**, aucun doublon en base ;
3. déconnexion puis rejeu du cookie : **401**.

Le quatrième critère (page d'inscription sous 200 Ko) **n'est pas vérifiable** : le client web n'existe pas. Le déclarer explicitement comme tel, ne pas le cocher.

- [ ] **Step 4 : nettoyer le compte de test créé à l'étape 3**

```bash
docker exec jobbot-postgres-1 psql -U jobbot -d jobbot \
  -c "delete from users where email like '%@example.sn';" \
  -c "select count(*) from users;" \
  -c "select count(*) from jobs;"
```
Expected: le compte de test parti, **232 offres intactes**.

- [ ] **Step 5 : pousser la branche**

```bash
git push
```

- [ ] **Step 6 : retitrer la PR #1 et réécrire sa description**

```bash
gh pr edit 1 --title "feat(phase-2): socle backend, API et authentification par email (sans Telegram)"
```

Réécrire le corps avec `gh pr edit 1 --body-file <fichier>`. La description actuelle décrit un bot, un téléphone obligatoire et une liaison de compte qui n'existent plus : elle mentirait sur le contenu de la branche. Le nouveau corps doit dire, au minimum : ce que la Phase 2 livre après le virage ; que Telegram et le téléphone ont été retirés le 2026-09-12 sur décision du porteur, avec un lien vers la spec ; que la faille du numéro non vérifié est fermée par la suppression de la colonne ; les comptes de tests **relevés à l'étape 1**, pas recopiés ; et que le client web reste à écrire, ce qui laisse le quatrième critère de validation de la Phase 2 non atteint.

- [ ] **Step 7 : signaler au porteur ce qui reste**

Dire explicitement, dans le rapport de fin :
- les trois critères de validation vérifiés et le quatrième non vérifiable, avec la raison ;
- que le plan du client web (`docs/superpowers/plans/2026-09-11-client-web.md`) n'existe pas et fait l'objet de sa propre séance de conception ;
- que `ADMIN_COURRIEL` est ajouté à la liste de contrôle du README mais ne bloque pas le démarrage, contrairement à `FOURNISSEUR_COURRIEL` ;
- qu'aucune commande CLI d'administration n'a été écrite, comme prévu (§5 de la spec).

---

## Auto-revue du plan

**Couverture de la spec :** §2 Portée → Tâches 1, 2, 3, 6 (suppressions) et 4 (schéma). §3 Modèle → Tâche 4. §4 Surface API → Tâches 2 et 4. §5 Canal d'administration → Tâche 5 (alertes) ; les commandes CLI sont hors périmètre par la spec elle-même, la Tâche 8 Step 7 le rappelle au porteur. §6 Configuration → Tâches 5 et 6. §7 Réécriture du CLAUDE.md → Tâche 7. §8 Critères de validation → Tâche 8. §9 Tests → répartis : suppressions en Tâches 1 et 3, adaptations en Tâches 2, 3, 4, 5, 6, ajouts en Tâches 1 (garde aiogram), 3 (garde téléphone), 4 (migration), 5 (AlerteCourriel), 6 (garde configuration). §10 Hors périmètre → rien à faire, rappelé en Tâche 8. §11 Arbitrages → rien à implémenter.

**Cohérence des noms entre tâches :** `AlerteJournalisee()` sans argument est introduit en Tâche 5 Step 5 et son appel corrigé au même Step 9. `AlerteCourriel(destinataire, fournisseur)` porte les mêmes noms d'attributs dans le test (Step 1) et l'implémentation (Step 5). `envoyer_message(destinataire, sujet, corps)` a la même signature dans le protocole (Step 3), le fournisseur console (Step 4), l'espion des tests (Step 8) et l'espion de `test_alerting.py` (Step 1). `admin_courriel` est ajouté en Tâche 5 Step 7 et vérifié absent de toute forme Telegram en Tâche 6 Step 1. Les helpers `_fichiers_src()` et `_modules_importes()` sont définis en Tâche 1 Step 1 et réutilisés sans redéfinition.

**Point d'attention pour l'exécutant :** la Tâche 3 Step 9 prévient que des tests d'intégration écrivent encore `phone=` et ne casseront qu'en Tâche 4. C'est attendu. Un échec plus tôt signale un vrai problème.
