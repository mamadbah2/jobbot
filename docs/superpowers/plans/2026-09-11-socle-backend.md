# Phase 2 — Socle backend et comptes — Plan d'implémentation

> **Pour les agents qui exécutent ce plan :** SOUS-COMPÉTENCE REQUISE — utiliser
> `superpowers:subagent-driven-development` (recommandé) ou `superpowers:executing-plans`
> pour dérouler ce plan tâche par tâche. Les étapes utilisent la syntaxe case à cocher
> (`- [ ]`) pour le suivi.

**Objectif :** extraire une couche métier réutilisable, l'exposer par une API FastAPI, et
authentifier les utilisateurs par email + code à 6 chiffres, sans mot de passe.

**Architecture :** `src/core/` contient le métier pur — il n'importe ni `fastapi` ni `aiogram`,
et un test le vérifie. `src/api/` le traduit en HTTP ; `src/bot/` l'appelle en direct dans son
process, sans passer par HTTP. L'envoi d'email passe par une abstraction dont la seule
implémentation, en Phase 2, écrit le code dans les logs.

**Stack :** Python 3.11, FastAPI, SQLAlchemy 2 async, Alembic, Redis, pyjwt, phonenumbers,
email-validator, pytest + pytest-asyncio.

**Spec :** `docs/superpowers/specs/2026-09-11-socle-backend-design.md` — à lire avant la tâche 1.
Le plan argumente depuis la spec ; les deux voyagent ensemble.

**Périmètre :** ce plan couvre **le backend seul**. Le client Next.js fait l'objet d'un plan
distinct (`2026-09-11-client-web.md`, à écrire après celui-ci) : à la fin de ce plan, l'API est
complète et utilisable au `curl`, ce qui en fait un livrable testable par lui-même.

## Contraintes globales

Ces règles s'appliquent à **toutes** les tâches. Valeurs reprises telles quelles de CLAUDE.md.

- Python 3.11+. **Type hints partout ; `mypy --strict` doit passer sur `src/`** (§13).
- `ruff` : `line-length = 100`, règles `E, F, I, B, UP, SIM`.
- **Aucun `print()`.** `structlog` uniquement, via `src.logging_setup.get_logger(__name__)` (§13).
- **Tous les textes destinés à l'utilisateur vivent dans `src/bot/texts.py`**, jamais en ligne (§4).
  Les messages d'erreur de l'API sont des **codes** stables, pas des phrases.
- **Vouvoiement partout**, français simple, sans jargon RH (§11).
- Aucun secret en dur (§13). Toute valeur métier passe par `src/config.py` (§3).
- **Aucune dépendance ajoutée sans justification écrite** (§3). Les quatre de ce plan sont
  justifiées au §12 de CLAUDE.md ; ne pas en ajouter d'autres.
- Toutes les dates en **UTC**, colonnes `TIMESTAMPTZ` (§5).
- Tables créées par Alembic uniquement, **jamais** `create_all` (§5).
- **`src/core/` n'importe ni `fastapi`, ni `aiogram`, ni `starlette`.** Vérifié par la tâche 17.
- **Le code de vérification n'apparaît dans aucun log**, à la seule exception de
  `src/courriel/console.py` (§2, interdiction n°2).
- Commits atomiques, messages **en français**, format `feat(scope): description` (§13).
- Les tests unitaires ne touchent **ni le réseau ni la base** (`tests/conftest.py`).

---

## Structure des fichiers

| Fichier | Responsabilité |
|---|---|
| `src/core/cache.py` | Protocol `CacheRedis` partagé par `codes.py` et `limites.py` |
| `src/core/erreurs.py` | Exceptions métier, traduites par chaque client |
| `src/core/telephone.py` | Normalisation E.164 sénégalaise |
| `src/core/courriel_valide.py` | Validation et normalisation d'adresse email |
| `src/core/auth/codes.py` | Génération, dépôt, vérification du code à 6 chiffres |
| `src/core/auth/limites.py` | Garde-fous anti-abus de l'envoi |
| `src/core/auth/jetons.py` | Encodage/décodage JWT + contrôle de `token_version` |
| `src/core/auth/comptes.py` | Création, récupération, liaison Telegram, révocation |
| `src/courriel/provider.py` | Interface `FournisseurCourriel` + fabrique |
| `src/courriel/console.py` | Implémentation de développement (logs) |
| `src/api/app.py` | Construction de l'app, gestionnaires d'exceptions |
| `src/api/deps.py` | Dépendances : session DB, cache, utilisateur courant |
| `src/api/schemas/auth.py` | Entrées/sorties pydantic de l'authentification |
| `src/api/routers/auth.py` | `/auth/code/demande`, `/auth/code/verifie`, `/auth/deconnexion` |
| `src/api/routers/moi.py` | `/moi`, `/moi/telegram/jeton` |
| `src/api/routers/sante.py` | `/health` — déplacé depuis `src/health.py`, qui est supprimé |
| `src/api/main.py` | Entrypoint du process `api` |
| `src/bot/handlers/compte.py` | Liaison par « partager mon contact » |

Découpage par responsabilité, pas par couche technique : `codes.py` ne connaît que Redis et le
hachage, `comptes.py` ne connaît que la base, `limites.py` ne connaît que les compteurs. Chacun
se teste seul, sans monter une app FastAPI.

---

## Tâche 1 : normalisation des numéros de téléphone

**Fichiers :**
- Créer : `src/core/__init__.py`, `src/core/telephone.py`
- Modifier : `pyproject.toml` (dépendance `phonenumbers`)
- Test : `tests/test_telephone.py`

**Interfaces :**
- Consomme : rien
- Produit : `normaliser(numero: str) -> str` — rend une chaîne E.164 (`+221771234567`),
  lève `NumeroInvalide` (défini en tâche 3 ; d'ici là, une `ValueError`).

> **Décision à respecter :** seuls les numéros **sénégalais** sont acceptés. Le paiement du §10
> passe par Wave / Orange Money / Free Money, qui sont tous sénégalais, et `users.phone` sert
> justement à ce paiement. Un numéro étranger serait accepté à l'inscription puis refusé au
> paiement — c'est le pire moment pour découvrir le problème.

- [ ] **Étape 1 : ajouter la dépendance**

Dans `pyproject.toml`, section `[project] dependencies`, après `"selectolax>=0.3.21",` :

```toml
    "phonenumbers>=8.13",
```

Puis : `uv pip install -e '.[dev]'` (ou `pip install -e '.[dev]'`).

- [ ] **Étape 2 : écrire le test qui échoue**

Créer `tests/test_telephone.py` :

```python
"""Normalisation des numéros (CLAUDE.md §5 : users.phone est unique et obligatoire)."""

from __future__ import annotations

import pytest

from src.core.telephone import normaliser

ATTENDU = "+221771234567"


@pytest.mark.parametrize(
    "saisie",
    [
        "+221771234567",
        "+221 77 123 45 67",
        "00221771234567",
        "221771234567",
        "771234567",
        "77 123 45 67",
        "  77-123-45-67  ",
    ],
)
def test_formats_locaux_acceptes(saisie: str) -> None:
    assert normaliser(saisie) == ATTENDU


@pytest.mark.parametrize(
    "saisie",
    [
        "",
        "   ",
        "bonjour",
        "12345",
        "7712345",            # trop court
        "+33612345678",       # numéro français : hors Sénégal
        "+1 415 555 0132",    # numéro américain
    ],
)
def test_numeros_refuses(saisie: str) -> None:
    with pytest.raises(ValueError):
        normaliser(saisie)


def test_numero_fixe_senegalais_accepte() -> None:
    assert normaliser("338591010") == "+221338591010"
```

- [ ] **Étape 3 : lancer le test et vérifier qu'il échoue**

Lancer : `pytest tests/test_telephone.py -v`
Attendu : ÉCHEC, `ModuleNotFoundError: No module named 'src.core'`

- [ ] **Étape 4 : écrire l'implémentation minimale**

Créer `src/core/__init__.py` :

```python
"""Métier pur : ce package n'importe ni fastapi, ni aiogram, ni starlette.

C'est la condition qui permet à l'API et au bot d'être deux traductions de la
même règle, et non deux copies. Vérifié par `tests/test_core_isole.py`.
"""
```

Créer `src/core/telephone.py` :

```python
"""Normalisation des numéros de téléphone sénégalais (CLAUDE.md §5).

`users.phone` est unique et obligatoire : il sert d'une part à retrouver un compte
depuis le bouton « partager mon contact » de Telegram, d'autre part au paiement
mobile money (§10). Deux écritures d'un même numéro doivent donc produire la même
chaîne, sinon l'unicité ne protège rien et un utilisateur crée un doublon en
tapant « 77 123 45 67 » au lieu de « +221771234567 ».

Seul le Sénégal est accepté : Wave, Orange Money et Free Money le sont aussi.
"""

from __future__ import annotations

import phonenumbers

REGION = "SN"


def normaliser(numero: str) -> str:
    """Rend le numéro au format E.164, ou lève `ValueError`."""
    brut = numero.strip()
    if not brut:
        raise ValueError("numero_vide")

    try:
        analyse = phonenumbers.parse(brut, REGION)
    except phonenumbers.NumberParseException as exc:
        raise ValueError("numero_illisible") from exc

    if not phonenumbers.is_valid_number(analyse):
        raise ValueError("numero_invalide")

    # `parse` avec une région de repli accepte un numéro étranger écrit en
    # international : on revérifie explicitement le pays.
    if phonenumbers.region_code_for_number(analyse) != REGION:
        raise ValueError("numero_hors_senegal")

    return phonenumbers.format_number(analyse, phonenumbers.PhoneNumberFormat.E164)
```

- [ ] **Étape 5 : lancer les tests et vérifier qu'ils passent**

Lancer : `pytest tests/test_telephone.py -v && mypy src/core/telephone.py`
Attendu : tous les tests PASSENT, `mypy` sans erreur.

- [ ] **Étape 6 : commiter**

```bash
git add pyproject.toml src/core/__init__.py src/core/telephone.py tests/test_telephone.py
git commit -m "feat(core): normalisation E.164 des numéros sénégalais"
```

---

## Tâche 2 : validation des adresses email

**Fichiers :**
- Créer : `src/core/courriel_valide.py`
- Modifier : `pyproject.toml` (dépendance `email-validator`)
- Test : `tests/test_courriel_valide.py`

**Interfaces :**
- Consomme : rien
- Produit : `normaliser(adresse: str) -> str` — rend l'adresse normalisée en minuscules,
  lève `ValueError`.

- [ ] **Étape 1 : ajouter la dépendance**

Dans `pyproject.toml`, après `"phonenumbers>=8.13",` :

```toml
    "email-validator>=2.2",
```

- [ ] **Étape 2 : écrire le test qui échoue**

Créer `tests/test_courriel_valide.py` :

```python
"""Validation d'adresse (CLAUDE.md §5 : users.email est l'identité de connexion)."""

from __future__ import annotations

import pytest

from src.core.courriel_valide import normaliser


def test_adresse_simple() -> None:
    assert normaliser("fatou@example.sn") == "fatou@example.sn"


def test_casse_et_espaces_normalises() -> None:
    assert normaliser("  Fatou.Diop@Example.SN  ") == "Fatou.Diop@example.sn"


def test_deux_ecritures_du_meme_domaine_convergent() -> None:
    # L'unicité de users.email ne protège rien si le domaine n'est pas normalisé.
    assert normaliser("a@EXAMPLE.sn") == normaliser("a@example.SN")


@pytest.mark.parametrize(
    "saisie",
    ["", "   ", "fatou", "fatou@", "@example.sn", "fatou@@example.sn", "fatou example@a.sn"],
)
def test_adresses_refusees(saisie: str) -> None:
    with pytest.raises(ValueError):
        normaliser(saisie)
```

> **Note sur la casse :** la partie locale (`Fatou.Diop`) est **conservée** telle quelle, seul le
> domaine est mis en minuscules. C'est la norme : la partie locale est sensible à la casse. Si un
> jour on veut la replier aussi, ce sera une décision explicite, pas un effet de bord.

- [ ] **Étape 3 : lancer le test et vérifier qu'il échoue**

Lancer : `pytest tests/test_courriel_valide.py -v`
Attendu : ÉCHEC, `ModuleNotFoundError: No module named 'src.core.courriel_valide'`

- [ ] **Étape 4 : écrire l'implémentation minimale**

Créer `src/core/courriel_valide.py` :

```python
"""Validation et normalisation des adresses email (CLAUDE.md §5).

`users.email` est unique : sans normalisation du domaine, `a@Example.sn` et
`a@example.sn` créeraient deux comptes pour la même boîte.

`check_deliverability=False` est délibéré : la vérification DNS est un appel
réseau. Elle rendrait les tests unitaires dépendants du réseau (interdit par
`tests/conftest.py`) et ferait échouer une inscription quand le VPS a un
souci de résolution — alors que l'adresse, elle, est bonne. Une adresse qui
n'existe pas se manifeste de toute façon par un code qui n'arrive jamais.
"""

from __future__ import annotations

from email_validator import EmailNotValidError, validate_email


def normaliser(adresse: str) -> str:
    """Rend l'adresse normalisée, ou lève `ValueError`."""
    brut = adresse.strip()
    if not brut:
        raise ValueError("adresse_vide")

    try:
        resultat = validate_email(brut, check_deliverability=False)
    except EmailNotValidError as exc:
        raise ValueError("adresse_invalide") from exc

    return str(resultat.normalized)
```

- [ ] **Étape 5 : lancer les tests et vérifier qu'ils passent**

Lancer : `pytest tests/test_courriel_valide.py -v && mypy src/core/courriel_valide.py`
Attendu : tous les tests PASSENT.

- [ ] **Étape 6 : commiter**

```bash
git add pyproject.toml src/core/courriel_valide.py tests/test_courriel_valide.py
git commit -m "feat(core): validation et normalisation des adresses email"
```

---

## Tâche 3 : exceptions métier

**Fichiers :**
- Créer : `src/core/erreurs.py`
- Modifier : `src/core/telephone.py`, `src/core/courriel_valide.py` (lever les vraies exceptions)
- Test : `tests/test_erreurs.py`, plus mise à jour de `tests/test_telephone.py` et
  `tests/test_courriel_valide.py`

**Interfaces :**
- Consomme : rien
- Produit : `ErreurMetier` et ses sous-classes, chacune portant un `code: str` stable.
  `TropDeDemandes` porte en plus `attendre_secondes: int`.

> **Pourquoi un `code` et pas un message :** les messages destinés à l'utilisateur vivent dans
> `src/bot/texts.py` côté bot, et dans le client web côté web (§4). L'API renvoie un identifiant
> stable que chaque client traduit dans sa langue et son ton. Un message dans l'exception serait
> un texte utilisateur égaré hors de `texts.py`.

- [ ] **Étape 1 : écrire le test qui échoue**

Créer `tests/test_erreurs.py` :

```python
"""Les erreurs métier portent un code stable, jamais un texte utilisateur."""

from __future__ import annotations

import pytest

from src.core import erreurs


def test_toutes_les_erreurs_derivent_d_erreur_metier() -> None:
    for nom in erreurs.__all__:
        classe = getattr(erreurs, nom)
        if classe is erreurs.ErreurMetier:
            continue
        assert issubclass(classe, erreurs.ErreurMetier), nom


def test_chaque_erreur_porte_un_code_non_vide() -> None:
    for nom in erreurs.__all__:
        classe = getattr(erreurs, nom)
        if classe is erreurs.ErreurMetier:
            continue
        assert isinstance(classe.code, str) and classe.code, nom


def test_les_codes_sont_uniques() -> None:
    codes = [
        getattr(erreurs, nom).code
        for nom in erreurs.__all__
        if getattr(erreurs, nom) is not erreurs.ErreurMetier
    ]
    assert len(codes) == len(set(codes))


def test_trop_de_demandes_porte_le_delai() -> None:
    exc = erreurs.TropDeDemandes(attendre_secondes=42)
    assert exc.attendre_secondes == 42
    assert exc.code == "trop_de_demandes"


def test_numero_invalide_est_bien_une_value_error() -> None:
    # Les appelants écrits avant cette tâche attrapent ValueError : ne pas les casser.
    assert issubclass(erreurs.NumeroInvalide, ValueError)
    with pytest.raises(ValueError):
        raise erreurs.NumeroInvalide("numero_hors_senegal")
```

- [ ] **Étape 2 : lancer le test et vérifier qu'il échoue**

Lancer : `pytest tests/test_erreurs.py -v`
Attendu : ÉCHEC, `ImportError: cannot import name 'erreurs'`

- [ ] **Étape 3 : écrire l'implémentation minimale**

Créer `src/core/erreurs.py` :

```python
"""Exceptions métier, traduites par chaque client (CLAUDE.md §4).

Chacune porte un `code` stable. L'API le renvoie tel quel, le bot le traduit via
`src/bot/texts.py`, le client web via ses propres libellés. Aucun texte destiné à
un utilisateur ne doit apparaître ici.
"""

from __future__ import annotations

__all__ = [
    "ErreurMetier",
    "NumeroInvalide",
    "AdresseInvalide",
    "TropDeDemandes",
    "PlafondGlobalAtteint",
    "CodeInvalide",
    "CodeExpire",
    "CompteInexistant",
    "InscriptionIncomplete",
    "TelephoneDejaUtilise",
    "ContactUsurpe",
    "JetonInvalide",
]


class ErreurMetier(Exception):
    """Racine des erreurs métier. `code` identifie le cas pour les clients."""

    code = "erreur_metier"


class NumeroInvalide(ErreurMetier, ValueError):
    code = "numero_invalide"


class AdresseInvalide(ErreurMetier, ValueError):
    code = "adresse_invalide"


class TropDeDemandes(ErreurMetier):
    """Un garde-fou du §10 de la spec a été atteint."""

    code = "trop_de_demandes"

    def __init__(self, *, attendre_secondes: int) -> None:
        super().__init__(self.code)
        self.attendre_secondes = attendre_secondes


class PlafondGlobalAtteint(ErreurMetier):
    """Plafond journalier de tout le service. Déclenche une alerte admin."""

    code = "plafond_global_atteint"


class CodeInvalide(ErreurMetier):
    code = "code_invalide"


class CodeExpire(ErreurMetier):
    """Code absent de Redis : expiré, jamais demandé, ou détruit après trop d'essais."""

    code = "code_expire"


class CompteInexistant(ErreurMetier):
    """Signal INTERNE. Ne doit jamais sortir de /auth/code/demande (spec §8)."""

    code = "compte_inexistant"


class InscriptionIncomplete(ErreurMetier):
    """Code valide, mais le compte est nouveau et nom/téléphone manquent."""

    code = "inscription_incomplete"


class TelephoneDejaUtilise(ErreurMetier):
    code = "telephone_deja_utilise"


class ContactUsurpe(ErreurMetier):
    """Contact Telegram partagé qui n'appartient pas à celui qui l'envoie."""

    code = "contact_usurpe"


class JetonInvalide(ErreurMetier):
    code = "jeton_invalide"
```

- [ ] **Étape 4 : brancher les deux modules existants**

Dans `src/core/telephone.py`, remplacer l'import et les quatre `raise ValueError(...)` :

```python
from src.core.erreurs import NumeroInvalide
```

puis `raise ValueError("numero_vide")` → `raise NumeroInvalide("numero_vide")`, et de même pour
`numero_illisible`, `numero_invalide`, `numero_hors_senegal` (garder `from exc` là où il y est).

Dans `src/core/courriel_valide.py` :

```python
from src.core.erreurs import AdresseInvalide
```

puis `raise ValueError("adresse_vide")` → `raise AdresseInvalide("adresse_vide")` et
`raise ValueError("adresse_invalide") from exc` → `raise AdresseInvalide("adresse_invalide") from exc`.

Les tests des tâches 1 et 2 attrapent `ValueError` et continuent de passer, puisque
`NumeroInvalide` et `AdresseInvalide` en héritent.

- [ ] **Étape 5 : lancer les tests et vérifier qu'ils passent**

Lancer : `pytest tests/test_erreurs.py tests/test_telephone.py tests/test_courriel_valide.py -v && mypy src/core/`
Attendu : tous les tests PASSENT.

- [ ] **Étape 6 : commiter**

```bash
git add src/core/erreurs.py src/core/telephone.py src/core/courriel_valide.py tests/test_erreurs.py
git commit -m "feat(core): exceptions métier à code stable"
```

---

## Tâche 4 : réglages de la Phase 2

**Fichiers :**
- Modifier : `src/config.py`, `.env.example`
- Test : `tests/test_config.py` (compléter le fichier existant)

**Interfaces :**
- Consomme : rien
- Produit : sur `Settings` — `jwt_secret: SecretStr`, `jwt_duree_jours: int`,
  `code_ttl_secondes: int`, `code_essais_max: int`, `auth_cooldown_secondes: int`,
  `auth_envois_par_heure: int`, `auth_envois_par_jour: int`, `auth_envois_par_ip_heure: int`,
  `auth_plafond_global_jour: int`, `fournisseur_courriel: str`, `cookie_session_nom: str`,
  `cookie_session_secure: bool` (propriété), `telegram_bot_username: str`.

> **Point sensible :** `jwt_secret` vide est toléré en `dev` (on génère un secret éphémère) mais
> doit **faire échouer le démarrage en `prod`**. Le §13 interdit les secrets en dur ; un secret
> par défaut publiquement documenté — comme l'est déjà `jobbot_dev_password` dans un dépôt
> public — permettrait de forger des jetons pour n'importe quel compte.

- [ ] **Étape 1 : écrire le test qui échoue**

Ajouter à `tests/test_config.py` :

```python
def test_jwt_secret_absent_refuse_en_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un secret vide en production permettrait de forger n'importe quel jeton."""
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        get_settings()


def test_jwt_secret_absent_tolere_en_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.jwt_secret.get_secret_value()  # secret éphémère généré


def test_garde_fous_auth_valeurs_par_defaut() -> None:
    settings = get_settings()
    assert settings.code_ttl_secondes == 300
    assert settings.code_essais_max == 5
    assert settings.auth_cooldown_secondes == 60
    assert settings.auth_envois_par_heure == 3
    assert settings.auth_envois_par_jour == 10
    assert settings.auth_envois_par_ip_heure == 10
    assert settings.auth_plafond_global_jour == 500
    assert settings.jwt_duree_jours == 30


def test_cookie_secure_suit_l_environnement(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "dev")
    get_settings.cache_clear()
    assert get_settings().cookie_session_secure is False
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("JWT_SECRET", "secret_de_test")
    get_settings.cache_clear()
    assert get_settings().cookie_session_secure is True


def test_secret_jwt_absent_du_dump(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le secret ne doit pas fuiter dans les logs via model_dump()."""
    monkeypatch.setenv("JWT_SECRET", "ne_doit_pas_apparaitre")
    get_settings.cache_clear()
    assert "ne_doit_pas_apparaitre" not in str(get_settings().model_dump())
```

Vérifier que le haut de `tests/test_config.py` importe bien `pytest`, `ValidationError`
(`from pydantic import ValidationError`) et `get_settings` ; ajouter ce qui manque.

- [ ] **Étape 2 : lancer le test et vérifier qu'il échoue**

Lancer : `pytest tests/test_config.py -v`
Attendu : ÉCHEC, `AttributeError: 'Settings' object has no attribute 'jwt_secret'`

- [ ] **Étape 3 : écrire l'implémentation minimale**

Dans `src/config.py`, ajouter aux imports :

```python
import secrets

from pydantic import Field, SecretStr, model_validator
```

Ajouter les champs après le bloc `# --- Redis ---` :

```python
    # --- Authentification (spec Phase 2, §5 et §10) ---
    # Vide autorisé en dev seulement : voir le validateur plus bas.
    jwt_secret: SecretStr = SecretStr("")
    jwt_duree_jours: int = Field(default=30, ge=1)
    cookie_session_nom: str = "jobbot_session"
    telegram_bot_username: str = ""

    # Le code vit en Redis, haché, et expire tout seul (§2, interdiction n°2).
    code_ttl_secondes: int = Field(default=300, ge=60)
    code_essais_max: int = Field(default=5, ge=1)

    # Garde-fous de l'envoi. L'endpoint est public : non protégé, il permet
    # d'inonder l'adresse d'un tiers et de brûler la réputation du domaine (§7).
    auth_cooldown_secondes: int = Field(default=60, ge=0)
    auth_envois_par_heure: int = Field(default=3, ge=1)
    auth_envois_par_jour: int = Field(default=10, ge=1)
    auth_envois_par_ip_heure: int = Field(default=10, ge=1)
    auth_plafond_global_jour: int = Field(default=500, ge=1)

    fournisseur_courriel: str = "console"
```

Ajouter le validateur après les champs :

```python
    @model_validator(mode="after")
    def _exiger_un_secret_en_prod(self) -> Settings:
        """En prod, un secret vide permettrait de forger n'importe quel jeton."""
        if self.jwt_secret.get_secret_value():
            return self
        if self.is_prod:
            raise ValueError(
                "JWT_SECRET est obligatoire en production. "
                "Générez-le avec : python -c 'import secrets; print(secrets.token_urlsafe(48))'"
            )
        # En dev, un secret éphémère : les jetons ne survivent pas à un redémarrage,
        # ce qui est sans conséquence et évite un secret par défaut publiquement connu.
        object.__setattr__(self, "jwt_secret", SecretStr(secrets.token_urlsafe(48)))
        return self
```

Ajouter la propriété à côté de `is_prod` :

```python
    @property
    def cookie_session_secure(self) -> bool:
        """Cookie `Secure` en production ; en dev on travaille en HTTP."""
        return self.is_prod
```

- [ ] **Étape 4 : compléter `.env.example`**

Ajouter à la fin, avec les commentaires (le fichier est public, cf. dépôt GitHub) :

```bash
# --- Authentification (Phase 2) ---
# OBLIGATOIRE en production : sans lui, n'importe qui forge un jeton de session.
# Générer avec : python -c 'import secrets; print(secrets.token_urlsafe(48))'
JWT_SECRET=
JWT_DUREE_JOURS=30

# Garde-fous de l'envoi du code. L'endpoint est public : sans eux, on inonde
# l'adresse d'un tiers et on brûle la réputation du domaine d'envoi.
CODE_TTL_SECONDES=300
CODE_ESSAIS_MAX=5
AUTH_COOLDOWN_SECONDES=60
AUTH_ENVOIS_PAR_HEURE=3
AUTH_ENVOIS_PAR_JOUR=10
AUTH_ENVOIS_PAR_IP_HEURE=10
AUTH_PLAFOND_GLOBAL_JOUR=500

# `console` écrit le code dans les logs. Aucun email réel n'est envoyé tant
# qu'aucun nom de domaine n'existe (CLAUDE.md §14.1).
FOURNISSEUR_COURRIEL=console

# Sans @ — sert à construire le lien profond de liaison de compte.
TELEGRAM_BOT_USERNAME=
```

- [ ] **Étape 5 : lancer les tests et vérifier qu'ils passent**

Lancer : `pytest tests/test_config.py -v && mypy src/config.py`
Attendu : tous les tests PASSENT.

- [ ] **Étape 6 : commiter**

```bash
git add src/config.py .env.example tests/test_config.py
git commit -m "feat(config): réglages d'authentification et garde-fous d'envoi"
```

---

## Tâche 5 : Protocol de cache et codes de vérification

**Fichiers :**
- Créer : `src/core/cache.py`, `src/core/auth/__init__.py`, `src/core/auth/codes.py`
- Modifier : `tests/conftest.py` (fixture `faux_cache`)
- Test : `tests/test_auth_codes.py`

**Interfaces :**
- Consomme : `src.core.erreurs.CodeExpire`, `CodeInvalide`
- Produit :
  - `src.core.cache.CacheRedis` — Protocol : `get`, `set`, `delete`, `incr`, `expire`, `ttl`
  - `generer_code() -> str` — 6 chiffres, zéros de tête conservés
  - `async deposer(cache, adresse, code, *, secret, ttl_secondes) -> None`
  - `async verifier(cache, adresse, code, *, secret, essais_max) -> None` — lève `CodeExpire`
    ou `CodeInvalide`
  - `async oublier(cache, adresse, *, secret) -> None`

- [ ] **Étape 1 : ajouter la fixture de cache factice**

Ajouter à `tests/conftest.py` :

```python
class FauxCache:
    """Redis en mémoire, réduit à ce dont `core` a besoin.

    Les tests unitaires ne touchent ni le réseau ni la base : un vrai Redis
    en ferait des tests d'intégration.
    """

    def __init__(self) -> None:
        self.valeurs: dict[str, str] = {}
        self.ttl: dict[str, int] = {}

    async def get(self, name: str) -> str | None:
        return self.valeurs.get(name)

    async def set(
        self, name: str, value: str, *, ex: int | None = None, nx: bool = False
    ) -> bool:
        if nx and name in self.valeurs:
            return False
        self.valeurs[name] = value
        if ex is not None:
            self.ttl[name] = ex
        return True

    async def delete(self, *names: str) -> int:
        efface = 0
        for name in names:
            efface += 1 if self.valeurs.pop(name, None) is not None else 0
            self.ttl.pop(name, None)
        return efface

    async def incr(self, name: str) -> int:
        valeur = int(self.valeurs.get(name, "0")) + 1
        self.valeurs[name] = str(valeur)
        return valeur

    async def expire(self, name: str, time: int) -> bool:
        if name not in self.valeurs:
            return False
        self.ttl[name] = time
        return True

    async def expirer_maintenant(self, *names: str) -> None:
        """Helper de test : simule l'expiration du TTL, sans attendre."""
        await self.delete(*names)


@pytest.fixture
def faux_cache() -> FauxCache:
    return FauxCache()
```

- [ ] **Étape 2 : écrire le test qui échoue**

Créer `tests/test_auth_codes.py` :

```python
"""Codes de vérification (spec Phase 2 §5 : jamais en base, jamais dans les logs)."""

from __future__ import annotations

import pytest

from src.core.auth import codes
from src.core.erreurs import CodeExpire, CodeInvalide
from tests.conftest import FauxCache

SECRET = "secret_de_test"
ADRESSE = "fatou@example.sn"


def test_code_a_six_chiffres() -> None:
    for _ in range(200):
        code = codes.generer_code()
        assert len(code) == 6
        assert code.isdigit()


def test_codes_successifs_differents() -> None:
    """Un code prévisible rendrait la vérification inutile."""
    tires = {codes.generer_code() for _ in range(200)}
    assert len(tires) > 150


async def test_depot_puis_verification_reussie(faux_cache: FauxCache) -> None:
    await codes.deposer(faux_cache, ADRESSE, "123456", secret=SECRET, ttl_secondes=300)
    await codes.verifier(faux_cache, ADRESSE, "123456", secret=SECRET, essais_max=5)


async def test_le_code_en_clair_n_est_jamais_stocke(faux_cache: FauxCache) -> None:
    await codes.deposer(faux_cache, ADRESSE, "123456", secret=SECRET, ttl_secondes=300)
    contenu = "".join(faux_cache.valeurs.keys()) + "".join(faux_cache.valeurs.values())
    assert "123456" not in contenu
    assert ADRESSE not in contenu


async def test_mauvais_code_refuse(faux_cache: FauxCache) -> None:
    await codes.deposer(faux_cache, ADRESSE, "123456", secret=SECRET, ttl_secondes=300)
    with pytest.raises(CodeInvalide):
        await codes.verifier(faux_cache, ADRESSE, "000000", secret=SECRET, essais_max=5)


async def test_aucun_code_depose(faux_cache: FauxCache) -> None:
    with pytest.raises(CodeExpire):
        await codes.verifier(faux_cache, ADRESSE, "123456", secret=SECRET, essais_max=5)


async def test_code_detruit_apres_cinq_essais(faux_cache: FauxCache) -> None:
    await codes.deposer(faux_cache, ADRESSE, "123456", secret=SECRET, ttl_secondes=300)
    for _ in range(5):
        with pytest.raises(CodeInvalide):
            await codes.verifier(faux_cache, ADRESSE, "000000", secret=SECRET, essais_max=5)
    # Le bon code ne doit plus marcher : le code a été détruit, pas seulement compté.
    with pytest.raises(CodeExpire):
        await codes.verifier(faux_cache, ADRESSE, "123456", secret=SECRET, essais_max=5)


async def test_code_consomme_apres_succes(faux_cache: FauxCache) -> None:
    """Un code doit être à usage unique."""
    await codes.deposer(faux_cache, ADRESSE, "123456", secret=SECRET, ttl_secondes=300)
    await codes.verifier(faux_cache, ADRESSE, "123456", secret=SECRET, essais_max=5)
    with pytest.raises(CodeExpire):
        await codes.verifier(faux_cache, ADRESSE, "123456", secret=SECRET, essais_max=5)


async def test_deux_adresses_ne_se_melangent_pas(faux_cache: FauxCache) -> None:
    await codes.deposer(faux_cache, "a@example.sn", "111111", secret=SECRET, ttl_secondes=300)
    await codes.deposer(faux_cache, "b@example.sn", "222222", secret=SECRET, ttl_secondes=300)
    with pytest.raises(CodeInvalide):
        await codes.verifier(faux_cache, "a@example.sn", "222222", secret=SECRET, essais_max=5)
    await codes.verifier(faux_cache, "b@example.sn", "222222", secret=SECRET, essais_max=5)
```

- [ ] **Étape 3 : lancer le test et vérifier qu'il échoue**

Lancer : `pytest tests/test_auth_codes.py -v`
Attendu : ÉCHEC, `ModuleNotFoundError: No module named 'src.core.auth'`

- [ ] **Étape 4 : écrire l'implémentation minimale**

Créer `src/core/cache.py` :

```python
"""Le strict minimum de l'API Redis dont `core` a besoin.

Un Protocol plutôt qu'un client concret : les tests unitaires n'ont pas le droit
de toucher au réseau (`tests/conftest.py`), et `core` ne doit dépendre d'aucune
bibliothèque cliente.
"""

from __future__ import annotations

from typing import Any, Protocol


class CacheRedis(Protocol):
    async def get(self, name: str) -> Any: ...
    async def set(
        self, name: str, value: str, *, ex: int | None = None, nx: bool = False
    ) -> Any: ...
    async def delete(self, *names: str) -> Any: ...
    async def incr(self, name: str) -> int: ...
    async def expire(self, name: str, time: int) -> Any: ...
```

Créer `src/core/auth/__init__.py` :

```python
"""Authentification : codes à usage unique, jetons, garde-fous, comptes."""
```

Créer `src/core/auth/codes.py` :

```python
"""Codes de vérification à usage unique (CLAUDE.md §2, interdiction n°2).

Trois propriétés, chacune pour une raison précise :

- **Rien en clair.** L'adresse ET le code sont hachés en HMAC-SHA256 avant
  d'entrer en Redis. Un dump Redis n'expose ni qui s'inscrit, ni avec quel code.
- **Usage unique.** Le code est détruit dès qu'il a servi, sinon il resterait
  valable jusqu'à son TTL et un rejeu suffirait à ouvrir la session.
- **Nombre d'essais borné.** Sans cela, 10^6 essais suffisent à deviner six
  chiffres. Au-delà du plafond, le code est DÉTRUIT, pas simplement refusé :
  refuser laisserait l'attaquant redemander un envoi et reprendre son décompte.
"""

from __future__ import annotations

import hmac
import secrets
from hashlib import sha256

from src.core.cache import CacheRedis
from src.core.erreurs import CodeExpire, CodeInvalide

_PREFIXE = "jobbot:auth"


def generer_code() -> str:
    """Six chiffres tirés cryptographiquement, zéros de tête conservés."""
    return f"{secrets.randbelow(1_000_000):06d}"


def _empreinte(valeur: str, secret: str) -> str:
    return hmac.new(secret.encode(), valeur.encode(), sha256).hexdigest()


def _cle_code(adresse: str, secret: str) -> str:
    return f"{_PREFIXE}:code:{_empreinte(adresse, secret)}"


def _cle_essais(adresse: str, secret: str) -> str:
    return f"{_PREFIXE}:essais:{_empreinte(adresse, secret)}"


async def deposer(
    cache: CacheRedis, adresse: str, code: str, *, secret: str, ttl_secondes: int
) -> None:
    """Remplace tout code en cours et remet le compteur d'essais à zéro."""
    await cache.delete(_cle_essais(adresse, secret))
    await cache.set(
        _cle_code(adresse, secret), _empreinte(code, secret), ex=ttl_secondes
    )


async def oublier(cache: CacheRedis, adresse: str, *, secret: str) -> None:
    """Détruit le code et son compteur."""
    await cache.delete(_cle_code(adresse, secret), _cle_essais(adresse, secret))


async def verifier(
    cache: CacheRedis, adresse: str, code: str, *, secret: str, essais_max: int
) -> None:
    """Ne rend rien en cas de succès ; lève sinon. Le code est consommé."""
    attendu = await cache.get(_cle_code(adresse, secret))
    if attendu is None:
        raise CodeExpire(CodeExpire.code)

    if isinstance(attendu, bytes):
        attendu = attendu.decode()

    # `compare_digest` plutôt que `==` : une comparaison qui s'arrête au premier
    # caractère différent laisse fuiter le préfixe correct par son temps de réponse.
    if hmac.compare_digest(attendu, _empreinte(code, secret)):
        await oublier(cache, adresse, secret=secret)
        return

    essais = await cache.incr(_cle_essais(adresse, secret))
    if essais == 1:
        # Le compteur ne doit pas survivre au code lui-même.
        await cache.expire(_cle_essais(adresse, secret), 3600)
    if essais >= essais_max:
        await oublier(cache, adresse, secret=secret)

    raise CodeInvalide(CodeInvalide.code)
```

- [ ] **Étape 5 : lancer les tests et vérifier qu'ils passent**

Lancer : `pytest tests/test_auth_codes.py -v && mypy src/core/`
Attendu : tous les tests PASSENT.

- [ ] **Étape 6 : commiter**

```bash
git add src/core/cache.py src/core/auth/__init__.py src/core/auth/codes.py tests/test_auth_codes.py tests/conftest.py
git commit -m "feat(core): codes de vérification à usage unique, hachés en Redis"
```

---

## Tâche 6 : garde-fous anti-abus

**Fichiers :**
- Créer : `src/core/auth/limites.py`
- Test : `tests/test_auth_limites.py`

**Interfaces :**
- Consomme : `src.core.cache.CacheRedis`, `src.core.erreurs.TropDeDemandes`,
  `PlafondGlobalAtteint`, `src.alerting.AlerteAdmin`
- Produit :
  - `@dataclass(frozen=True, slots=True) class ReglesEnvoi` — champs `cooldown_secondes`,
    `par_heure`, `par_jour`, `par_ip_heure`, `plafond_global_jour`
  - `async autoriser_envoi(cache, *, adresse, ip, regles, secret, alerte) -> None`

> **Ordre des contrôles, et pourquoi il compte :** le cooldown est vérifié **en premier** et le
> plafond global **en dernier**. Un attaquant ne doit pas pouvoir consommer le plafond global du
> service — qui protège tout le monde — avant d'avoir été arrêté par sa propre limite.
> `autoriser_envoi` incrémente les compteurs : elle n'est appelée qu'une fois par demande.

- [ ] **Étape 1 : écrire le test qui échoue**

Créer `tests/test_auth_limites.py` :

```python
"""Garde-fous de l'envoi (spec Phase 2 §10).

L'endpoint est public : sans ces limites, on inonde l'adresse d'un tiers et on
brûle la réputation du futur domaine d'envoi.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.auth.limites import ReglesEnvoi, autoriser_envoi
from src.core.erreurs import PlafondGlobalAtteint, TropDeDemandes
from tests.conftest import FauxCache

SECRET = "secret_de_test"
ADRESSE = "fatou@example.sn"
IP = "41.82.0.1"

REGLES = ReglesEnvoi(
    cooldown_secondes=60, par_heure=3, par_jour=10, par_ip_heure=10, plafond_global_jour=500
)


class AlerteEspion:
    def __init__(self) -> None:
        self.recues: list[tuple[str, dict[str, Any]]] = []

    async def envoyer(self, evenement: str, **contexte: Any) -> None:
        self.recues.append((evenement, contexte))


async def demander(cache: FauxCache, alerte: AlerteEspion, regles: ReglesEnvoi = REGLES) -> None:
    await autoriser_envoi(
        cache, adresse=ADRESSE, ip=IP, regles=regles, secret=SECRET, alerte=alerte
    )


async def test_premier_envoi_autorise(faux_cache: FauxCache) -> None:
    await demander(faux_cache, AlerteEspion())


async def test_cooldown_bloque_le_second_envoi_immediat(faux_cache: FauxCache) -> None:
    alerte = AlerteEspion()
    await demander(faux_cache, alerte)
    with pytest.raises(TropDeDemandes) as info:
        await demander(faux_cache, alerte)
    assert info.value.attendre_secondes == 60


async def test_plafond_horaire_par_adresse(faux_cache: FauxCache) -> None:
    alerte = AlerteEspion()
    regles = ReglesEnvoi(
        cooldown_secondes=0, par_heure=3, par_jour=10, par_ip_heure=100, plafond_global_jour=500
    )
    for _ in range(3):
        await demander(faux_cache, alerte, regles)
    with pytest.raises(TropDeDemandes):
        await demander(faux_cache, alerte, regles)


async def test_plafond_journalier_par_adresse(faux_cache: FauxCache) -> None:
    alerte = AlerteEspion()
    regles = ReglesEnvoi(
        cooldown_secondes=0, par_heure=100, par_jour=10, par_ip_heure=100, plafond_global_jour=500
    )
    for _ in range(10):
        await demander(faux_cache, alerte, regles)
    with pytest.raises(TropDeDemandes):
        await demander(faux_cache, alerte, regles)


async def test_plafond_par_ip_independant_de_l_adresse(faux_cache: FauxCache) -> None:
    """Changer d'adresse ne doit pas remettre le compteur d'IP à zéro."""
    alerte = AlerteEspion()
    regles = ReglesEnvoi(
        cooldown_secondes=0, par_heure=100, par_jour=100, par_ip_heure=2, plafond_global_jour=500
    )
    for i in range(2):
        await autoriser_envoi(
            faux_cache, adresse=f"u{i}@example.sn", ip=IP, regles=regles, secret=SECRET,
            alerte=alerte,
        )
    with pytest.raises(TropDeDemandes):
        await autoriser_envoi(
            faux_cache, adresse="autre@example.sn", ip=IP, regles=regles, secret=SECRET,
            alerte=alerte,
        )


async def test_plafond_global_leve_et_alerte(faux_cache: FauxCache) -> None:
    """« Ne jamais échouer en silence » (CLAUDE.md §7)."""
    alerte = AlerteEspion()
    regles = ReglesEnvoi(
        cooldown_secondes=0, par_heure=100, par_jour=100, par_ip_heure=100, plafond_global_jour=2
    )
    for i in range(2):
        await autoriser_envoi(
            faux_cache, adresse=f"u{i}@example.sn", ip=f"41.82.0.{i}", regles=regles,
            secret=SECRET, alerte=alerte,
        )
    with pytest.raises(PlafondGlobalAtteint):
        await autoriser_envoi(
            faux_cache, adresse="trop@example.sn", ip="41.82.0.9", regles=regles,
            secret=SECRET, alerte=alerte,
        )
    assert [nom for nom, _ in alerte.recues] == ["plafond_global_envois_atteint"]


async def test_l_adresse_n_apparait_pas_en_clair_dans_les_cles(faux_cache: FauxCache) -> None:
    await demander(faux_cache, AlerteEspion())
    assert ADRESSE not in "".join(faux_cache.valeurs.keys())


async def test_le_plafond_global_n_est_pas_consomme_par_un_refus(faux_cache: FauxCache) -> None:
    """Un attaquant arrêté par SA limite ne doit pas entamer celle de tout le monde."""
    alerte = AlerteEspion()
    regles = ReglesEnvoi(
        cooldown_secondes=60, par_heure=3, par_jour=10, par_ip_heure=100, plafond_global_jour=500
    )
    await demander(faux_cache, alerte, regles)
    with pytest.raises(TropDeDemandes):
        await demander(faux_cache, alerte, regles)
    cle_globale = next(c for c in faux_cache.valeurs if "global" in c)
    assert faux_cache.valeurs[cle_globale] == "1"
```

- [ ] **Étape 2 : lancer le test et vérifier qu'il échoue**

Lancer : `pytest tests/test_auth_limites.py -v`
Attendu : ÉCHEC, `ModuleNotFoundError: No module named 'src.core.auth.limites'`

- [ ] **Étape 3 : écrire l'implémentation minimale**

Créer `src/core/auth/limites.py` :

```python
"""Garde-fous de l'envoi du code (spec Phase 2 §10).

`/auth/code/demande` est public et déclenche un email. Sans limite, il permet
d'inonder la boîte d'un tiers et de brûler la réputation du domaine d'envoi —
la ressource la plus lente à reconstruire du projet.

L'ordre des contrôles est délibéré : les limites de l'appelant d'abord, le
plafond global en dernier. Un attaquant arrêté par sa propre limite ne doit pas
avoir entamé le plafond qui protège tous les autres utilisateurs.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from src.alerting import AlerteAdmin
from src.core.cache import CacheRedis
from src.core.erreurs import PlafondGlobalAtteint, TropDeDemandes
from src.logging_setup import get_logger

log = get_logger(__name__)

_PREFIXE = "jobbot:auth:limite"
_HEURE = 3600
_JOUR = 86400


@dataclass(frozen=True, slots=True)
class ReglesEnvoi:
    """Plafonds applicables à une demande d'envoi. Tous configurables (§3)."""

    cooldown_secondes: int
    par_heure: int
    par_jour: int
    par_ip_heure: int
    plafond_global_jour: int


def _empreinte(valeur: str, secret: str) -> str:
    return hmac.new(secret.encode(), valeur.encode(), sha256).hexdigest()[:32]


def _fenetre_heure() -> str:
    return datetime.now(UTC).strftime("%Y%m%d%H")


def _fenetre_jour() -> str:
    return datetime.now(UTC).strftime("%Y%m%d")


async def _incrementer(cache: CacheRedis, cle: str, duree: int) -> int:
    """Compteur à fenêtre fixe : la clé porte la fenêtre, le TTL la nettoie."""
    valeur = await cache.incr(cle)
    if valeur == 1:
        await cache.expire(cle, duree)
    return int(valeur)


async def autoriser_envoi(
    cache: CacheRedis,
    *,
    adresse: str,
    ip: str,
    regles: ReglesEnvoi,
    secret: str,
    alerte: AlerteAdmin,
) -> None:
    """Ne rend rien si l'envoi est permis ; lève sinon. Consomme les compteurs."""
    empreinte = _empreinte(adresse, secret)

    if regles.cooldown_secondes > 0:
        pose = await cache.set(
            f"{_PREFIXE}:cooldown:{empreinte}", "1", ex=regles.cooldown_secondes, nx=True
        )
        if not pose:
            raise TropDeDemandes(attendre_secondes=regles.cooldown_secondes)

    heure = await _incrementer(
        cache, f"{_PREFIXE}:h:{empreinte}:{_fenetre_heure()}", _HEURE
    )
    if heure > regles.par_heure:
        raise TropDeDemandes(attendre_secondes=_HEURE)

    jour = await _incrementer(cache, f"{_PREFIXE}:j:{empreinte}:{_fenetre_jour()}", _JOUR)
    if jour > regles.par_jour:
        raise TropDeDemandes(attendre_secondes=_JOUR)

    ip_heure = await _incrementer(
        cache, f"{_PREFIXE}:ip:{_empreinte(ip, secret)}:{_fenetre_heure()}", _HEURE
    )
    if ip_heure > regles.par_ip_heure:
        raise TropDeDemandes(attendre_secondes=_HEURE)

    total = await _incrementer(cache, f"{_PREFIXE}:global:{_fenetre_jour()}", _JOUR)
    if total > regles.plafond_global_jour:
        # Ne jamais échouer en silence (§7) : ce plafond signale soit un abus,
        # soit un succès inattendu. Les deux méritent un réveil.
        await alerte.envoyer(
            "plafond_global_envois_atteint",
            plafond=regles.plafond_global_jour,
            compte=total,
        )
        raise PlafondGlobalAtteint(PlafondGlobalAtteint.code)
```

- [ ] **Étape 4 : lancer les tests et vérifier qu'ils passent**

Lancer : `pytest tests/test_auth_limites.py -v && mypy src/core/`
Attendu : tous les tests PASSENT.

- [ ] **Étape 5 : commiter**

```bash
git add src/core/auth/limites.py tests/test_auth_limites.py
git commit -m "feat(core): garde-fous anti-abus de l'envoi du code"
```

---

## Tâche 7 : jetons de session

**Fichiers :**
- Créer : `src/core/auth/jetons.py`
- Modifier : `pyproject.toml` (dépendance `pyjwt`)
- Test : `tests/test_auth_jetons.py`

**Interfaces :**
- Consomme : `src.core.erreurs.JetonInvalide`
- Produit :
  - `@dataclass(frozen=True, slots=True) class Revendications` — `user_id: int`, `token_version: int`
  - `encoder(*, user_id: int, token_version: int, secret: str, duree_jours: int) -> str`
  - `decoder(jeton: str, *, secret: str) -> Revendications` — lève `JetonInvalide`

- [ ] **Étape 1 : ajouter la dépendance**

Dans `pyproject.toml`, après `"email-validator>=2.2",` :

```toml
    "pyjwt>=2.9",
```

- [ ] **Étape 2 : écrire le test qui échoue**

Créer `tests/test_auth_jetons.py` :

```python
"""Jetons de session (spec Phase 2 §5 : pas de table de sessions)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from src.core.auth.jetons import Revendications, decoder, encoder
from src.core.erreurs import JetonInvalide

SECRET = "secret_de_test"


def test_aller_retour() -> None:
    jeton = encoder(user_id=7, token_version=3, secret=SECRET, duree_jours=30)
    assert decoder(jeton, secret=SECRET) == Revendications(user_id=7, token_version=3)


def test_signature_d_un_autre_secret_refusee() -> None:
    jeton = encoder(user_id=7, token_version=0, secret="autre_secret", duree_jours=30)
    with pytest.raises(JetonInvalide):
        decoder(jeton, secret=SECRET)


def test_jeton_altere_refuse() -> None:
    jeton = encoder(user_id=7, token_version=0, secret=SECRET, duree_jours=30)
    altere = jeton[:-4] + ("aaaa" if not jeton.endswith("aaaa") else "bbbb")
    with pytest.raises(JetonInvalide):
        decoder(altere, secret=SECRET)


def test_jeton_expire_refuse() -> None:
    passe = datetime.now(UTC) - timedelta(days=1)
    jeton = jwt.encode(
        {"sub": "7", "tv": 0, "exp": passe, "iat": passe}, SECRET, algorithm="HS256"
    )
    with pytest.raises(JetonInvalide):
        decoder(jeton, secret=SECRET)


def test_chaine_quelconque_refusee() -> None:
    with pytest.raises(JetonInvalide):
        decoder("pas-un-jeton", secret=SECRET)


def test_algorithme_none_refuse() -> None:
    """Attaque classique : un jeton signé `alg: none` ne doit jamais être accepté."""
    jeton = jwt.encode({"sub": "7", "tv": 0}, key="", algorithm="none")
    with pytest.raises(JetonInvalide):
        decoder(jeton, secret=SECRET)


def test_revendications_manquantes_refusees() -> None:
    futur = datetime.now(UTC) + timedelta(days=1)
    jeton = jwt.encode({"exp": futur}, SECRET, algorithm="HS256")
    with pytest.raises(JetonInvalide):
        decoder(jeton, secret=SECRET)
```

- [ ] **Étape 3 : lancer le test et vérifier qu'il échoue**

Lancer : `pytest tests/test_auth_jetons.py -v`
Attendu : ÉCHEC, `ModuleNotFoundError: No module named 'src.core.auth.jetons'`

- [ ] **Étape 4 : écrire l'implémentation minimale**

Créer `src/core/auth/jetons.py` :

```python
"""Jetons de session (spec Phase 2 §5).

Pas de table de sessions, pas de jeton de rafraîchissement : un seul jeton
d'accès de 30 jours portant `token_version`. On charge déjà l'utilisateur à
chaque requête authentifiée, donc comparer la version ne coûte rien de plus.
Se déconnecter de partout = incrémenter la colonne.

Prix assumé : un jeton volé reste valable jusqu'à révocation explicite.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from src.core.erreurs import JetonInvalide

ALGORITHME = "HS256"


@dataclass(frozen=True, slots=True)
class Revendications:
    """Ce qu'un jeton valide affirme."""

    user_id: int
    token_version: int


def encoder(*, user_id: int, token_version: int, secret: str, duree_jours: int) -> str:
    """Signe un jeton de session."""
    emission = datetime.now(UTC)
    charge = {
        "sub": str(user_id),
        "tv": token_version,
        "iat": emission,
        "exp": emission + timedelta(days=duree_jours),
    }
    return jwt.encode(charge, secret, algorithm=ALGORITHME)


def decoder(jeton: str, *, secret: str) -> Revendications:
    """Vérifie signature et expiration, ou lève `JetonInvalide`.

    `algorithms` est explicitement restreint : sans cette liste, un jeton forgé
    avec `alg: none` serait accepté sans aucune signature.
    """
    try:
        charge = jwt.decode(jeton, secret, algorithms=[ALGORITHME])
        return Revendications(user_id=int(charge["sub"]), token_version=int(charge["tv"]))
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise JetonInvalide(JetonInvalide.code) from exc
```

- [ ] **Étape 5 : lancer les tests et vérifier qu'ils passent**

Lancer : `pytest tests/test_auth_jetons.py -v && mypy src/core/`
Attendu : tous les tests PASSENT.

- [ ] **Étape 6 : commiter**

```bash
git add pyproject.toml src/core/auth/jetons.py tests/test_auth_jetons.py
git commit -m "feat(core): jetons de session JWT révocables par token_version"
```

---

## Tâche 8 : identité — modèles et migration `0002`

**Fichiers :**
- Modifier : `src/db/models.py:75-95` (classe `User`)
- Créer : `alembic/versions/0002_identite_email.py`
- Test : `tests/test_identite_migration.py`

**Interfaces :**
- Consomme : rien
- Produit : sur `User` — `email: Mapped[str]` (non nul, unique), `phone: Mapped[str]` (non nul,
  unique), `telegram_id: Mapped[int | None]`, `token_version: Mapped[int]`.

> **Contexte vérifié le 2026-09-11 : `users` contient 0 ligne** (contre 232 dans `jobs`). La
> migration ne demande donc aucun backfill. Si ce n'était plus vrai au moment de l'exécuter,
> **arrêter et le signaler** : passer une colonne à `NOT NULL UNIQUE` sur une table peuplée
> échouerait, et inventer des adresses serait pire.
>
> Dans `0001`, l'unicité de `telegram_id` vient d'un **index unique**
> (`ix_users_telegram_id`), pas d'une contrainte. En Postgres, un index unique autorise
> plusieurs `NULL` : rendre la colonne nullable ne casse donc rien. On reste sur des index
> uniques pour `email` et `phone`, par cohérence.

- [ ] **Étape 1 : écrire le test qui échoue**

Créer `tests/test_identite_migration.py` :

```python
"""Identité : email et téléphone obligatoires, telegram_id facultatif (CLAUDE.md §5).

Lancer avec : RUN_INTEGRATION_TESTS=1 pytest -m integration
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import delete, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models import User


def test_modele_user_declare_la_nouvelle_identite() -> None:
    colonnes = {c.name: c for c in User.__table__.columns}
    assert colonnes["email"].nullable is False
    assert colonnes["phone"].nullable is False
    assert colonnes["telegram_id"].nullable is True
    assert colonnes["token_version"].nullable is False
    assert colonnes["token_version"].default.arg == 0


@pytest_asyncio.fixture
async def session(postgres_url: str) -> AsyncIterator[AsyncSession]:
    moteur = create_async_engine(postgres_url)
    fabrique = async_sessionmaker(moteur, expire_on_commit=False)
    async with fabrique() as session:
        await session.execute(delete(User).where(User.email.like("%@jobbot-test.sn")))
        await session.commit()
        yield session
        await session.execute(delete(User).where(User.email.like("%@jobbot-test.sn")))
        await session.commit()
    await moteur.dispose()


@pytest.mark.integration
async def test_colonnes_presentes_en_base(session: AsyncSession) -> None:
    lignes = await session.execute(
        text(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_name = 'users'"
        )
    )
    etat = {nom: nullable for nom, nullable in lignes.all()}
    assert etat["email"] == "NO"
    assert etat["phone"] == "NO"
    assert etat["telegram_id"] == "YES"
    assert etat["token_version"] == "NO"


@pytest.mark.integration
async def test_compte_sans_telegram_accepte(session: AsyncSession) -> None:
    session.add(User(email="a@jobbot-test.sn", phone="+221771111111", full_name="A"))
    await session.commit()


@pytest.mark.integration
async def test_deux_comptes_sans_telegram_acceptes(session: AsyncSession) -> None:
    """Un index unique tolère plusieurs NULL : sinon un seul compte web serait possible."""
    session.add(User(email="b@jobbot-test.sn", phone="+221772222222", full_name="B"))
    session.add(User(email="c@jobbot-test.sn", phone="+221773333333", full_name="C"))
    await session.commit()


@pytest.mark.integration
async def test_adresse_en_double_refusee(session: AsyncSession) -> None:
    session.add(User(email="d@jobbot-test.sn", phone="+221774444444", full_name="D"))
    await session.commit()
    session.add(User(email="d@jobbot-test.sn", phone="+221775555555", full_name="D2"))
    with pytest.raises(IntegrityError):
        await session.commit()


@pytest.mark.integration
async def test_telephone_en_double_refuse(session: AsyncSession) -> None:
    session.add(User(email="e@jobbot-test.sn", phone="+221776666666", full_name="E"))
    await session.commit()
    session.add(User(email="f@jobbot-test.sn", phone="+221776666666", full_name="F"))
    with pytest.raises(IntegrityError):
        await session.commit()
```

- [ ] **Étape 2 : lancer le test et vérifier qu'il échoue**

Lancer : `pytest tests/test_identite_migration.py::test_modele_user_declare_la_nouvelle_identite -v`
Attendu : ÉCHEC, `KeyError: 'token_version'`

- [ ] **Étape 3 : modifier le modèle**

Dans `src/db/models.py`, remplacer le corps de la classe `User` (lignes ~75-95) par :

```python
    id: Mapped[int] = mapped_column(primary_key=True)
    # Identité de connexion depuis le 2026-09-11 (CLAUDE.md §5). Avant cette date
    # c'était `telegram_id`, quand Telegram était l'unique interface.
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    # Obligatoire : sert à retrouver un compte depuis « partager mon contact »
    # (bouton natif Telegram, numéro déjà vérifié) et au paiement mobile money (§10).
    phone: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    # Nullable : un utilisateur venu du web n'a pas encore lié Telegram.
    # En Postgres, un index unique tolère plusieurs NULL.
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    # Incrémentée pour invalider d'un coup tous les jetons émis (§5).
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="fr", nullable=False)
    state: Mapped[str] = mapped_column(String(16), default="onboarding", nullable=False)

    profile: Mapped[Profile | None] = relationship(back_populates="user", uselist=False)
```

- [ ] **Étape 4 : écrire la migration**

Créer `alembic/versions/0002_identite_email.py` :

```python
"""identite par email

Le 2026-09-11, `users.email` devient l'identité de connexion et `telegram_id`
n'est plus qu'un canal parmi d'autres (CLAUDE.md §2 et §5).

La table était VIDE au moment d'écrire cette migration (0 ligne, vérifié le
2026-09-11) : aucun backfill n'est donc nécessaire. Sur une table peuplée,
`nullable=False` sur `email` et `phone` échouerait — c'est voulu, mieux vaut
un échec bruyant qu'une adresse inventée.

Revision ID: a1c2e3f40002
Revises: 4bfafb92720f
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1c2e3f40002"
down_revision: str | None = "4bfafb92720f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "telegram_id", existing_type=sa.BigInteger(), nullable=True)
    op.alter_column("users", "email", existing_type=sa.String(length=320), nullable=False)
    op.alter_column("users", "phone", existing_type=sa.String(length=32), nullable=False)
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_phone"), "users", ["phone"], unique=True)
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), server_default="0", nullable=False),
    )
    # Le défaut serveur n'était là que pour remplir les lignes existantes ;
    # la valeur vient du modèle SQLAlchemy ensuite.
    op.alter_column("users", "token_version", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "token_version")
    op.drop_index(op.f("ix_users_phone"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.alter_column("users", "phone", existing_type=sa.String(length=32), nullable=True)
    op.alter_column("users", "email", existing_type=sa.String(length=320), nullable=True)
    op.alter_column("users", "telegram_id", existing_type=sa.BigInteger(), nullable=False)
```

- [ ] **Étape 5 : appliquer et vérifier**

```bash
docker compose up -d postgres redis
docker compose run --rm migrate
RUN_INTEGRATION_TESTS=1 pytest tests/test_identite_migration.py -m integration -v
pytest tests/test_identite_migration.py::test_modele_user_declare_la_nouvelle_identite tests/test_migrations.py -v
mypy src/db/models.py
```

Attendu : la migration s'applique, tous les tests PASSENT.

> Si `docker compose run --rm migrate` échoue avec du code absent, **reconstruire l'image** :
> `docker compose build`. L'image ne suit pas les fichiers montés — voir la note projet
> « piège de l'image Docker périmée ».

- [ ] **Étape 6 : commiter**

```bash
git add src/db/models.py alembic/versions/0002_identite_email.py tests/test_identite_migration.py
git commit -m "feat(db): l'email devient l'identité, telegram_id devient facultatif"
```

---

## Tâche 9 : comptes

**Fichiers :**
- Créer : `src/core/auth/comptes.py`
- Test : `tests/test_auth_comptes.py`

**Interfaces :**
- Consomme : `src.db.models.User`, `src.core.erreurs.*`, `src.core.telephone.normaliser`,
  `src.core.courriel_valide.normaliser`
- Produit :
  - `async par_adresse(session, adresse: str) -> User | None`
  - `async par_telephone(session, telephone: str) -> User | None`
  - `async par_telegram(session, telegram_id: int) -> User | None`
  - `async connecter_ou_inscrire(session, *, adresse, telephone_saisi=None, nom_complet=None) -> User`
    — lève `InscriptionIncomplete` si le compte est nouveau et qu'un champ manque,
    `TelephoneDejaUtilise` si le numéro appartient à un autre compte
  - `async lier_telegram(session, *, telephone, telegram_id) -> User` — lève `CompteInexistant`
  - `async revoquer_jetons(session, utilisateur: User) -> None`

- [ ] **Étape 1 : écrire le test qui échoue**

Créer `tests/test_auth_comptes.py` :

```python
"""Comptes (spec Phase 2 §8 et §9).

Lancer avec : RUN_INTEGRATION_TESTS=1 pytest -m integration
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.auth import comptes
from src.core.erreurs import (
    AdresseInvalide,
    CompteInexistant,
    InscriptionIncomplete,
    NumeroInvalide,
    TelephoneDejaUtilise,
)
from src.db.models import User

ADRESSE = "fatou@jobbot-test.sn"
TEL = "+221771234567"


@pytest_asyncio.fixture
async def session(postgres_url: str) -> AsyncIterator[AsyncSession]:
    moteur = create_async_engine(postgres_url)
    fabrique = async_sessionmaker(moteur, expire_on_commit=False)
    async with fabrique() as session:
        await session.execute(delete(User).where(User.email.like("%@jobbot-test.sn")))
        await session.commit()
        yield session
        await session.execute(delete(User).where(User.email.like("%@jobbot-test.sn")))
        await session.commit()
    await moteur.dispose()


@pytest.mark.integration
async def test_inscription_cree_le_compte(session: AsyncSession) -> None:
    u = await comptes.connecter_ou_inscrire(
        session, adresse=ADRESSE, telephone_saisi="77 123 45 67", nom_complet="Fatou Diop"
    )
    await session.commit()
    assert u.email == ADRESSE
    assert u.phone == TEL  # normalisé en E.164
    assert u.telegram_id is None
    assert u.token_version == 0
    assert u.state == "onboarding"


@pytest.mark.integration
async def test_reconnexion_ne_redemande_rien(session: AsyncSession) -> None:
    """Un utilisateur qui revient ne ressaisit jamais son numéro (spec §8)."""
    await comptes.connecter_ou_inscrire(
        session, adresse=ADRESSE, telephone_saisi=TEL, nom_complet="Fatou Diop"
    )
    await session.commit()
    u = await comptes.connecter_ou_inscrire(session, adresse=ADRESSE)
    assert u.phone == TEL
    assert u.full_name == "Fatou Diop"


@pytest.mark.integration
async def test_reconnexion_ignore_les_champs_fournis(session: AsyncSession) -> None:
    """Sinon /auth/code/verifie deviendrait un moyen d'écraser le numéro d'un compte."""
    await comptes.connecter_ou_inscrire(
        session, adresse=ADRESSE, telephone_saisi=TEL, nom_complet="Fatou Diop"
    )
    await session.commit()
    u = await comptes.connecter_ou_inscrire(
        session, adresse=ADRESSE, telephone_saisi="+221779999999", nom_complet="Autre Nom"
    )
    assert u.phone == TEL
    assert u.full_name == "Fatou Diop"


@pytest.mark.integration
async def test_inscription_sans_telephone_refusee(session: AsyncSession) -> None:
    with pytest.raises(InscriptionIncomplete):
        await comptes.connecter_ou_inscrire(session, adresse=ADRESSE, nom_complet="Fatou")


@pytest.mark.integration
async def test_inscription_sans_nom_refusee(session: AsyncSession) -> None:
    with pytest.raises(InscriptionIncomplete):
        await comptes.connecter_ou_inscrire(session, adresse=ADRESSE, telephone_saisi=TEL)


@pytest.mark.integration
async def test_telephone_deja_pris_par_un_autre_compte(session: AsyncSession) -> None:
    await comptes.connecter_ou_inscrire(
        session, adresse=ADRESSE, telephone_saisi=TEL, nom_complet="Fatou"
    )
    await session.commit()
    with pytest.raises(TelephoneDejaUtilise):
        await comptes.connecter_ou_inscrire(
            session, adresse="autre@jobbot-test.sn", telephone_saisi=TEL, nom_complet="Autre"
        )


@pytest.mark.integration
async def test_adresse_normalisee_avant_recherche(session: AsyncSession) -> None:
    await comptes.connecter_ou_inscrire(
        session, adresse=ADRESSE, telephone_saisi=TEL, nom_complet="Fatou"
    )
    await session.commit()
    u = await comptes.connecter_ou_inscrire(session, adresse="fatou@TEST.INVALID")
    assert u.email == ADRESSE


@pytest.mark.integration
async def test_saisies_invalides_refusees(session: AsyncSession) -> None:
    with pytest.raises(AdresseInvalide):
        await comptes.connecter_ou_inscrire(session, adresse="pas-une-adresse")
    with pytest.raises(NumeroInvalide):
        await comptes.connecter_ou_inscrire(
            session, adresse=ADRESSE, telephone_saisi="+33612345678", nom_complet="Fatou"
        )


@pytest.mark.integration
async def test_liaison_telegram_retrouve_le_compte(session: AsyncSession) -> None:
    """Le cœur du §9 : pas de doublon entre le web et Telegram."""
    cree = await comptes.connecter_ou_inscrire(
        session, adresse=ADRESSE, telephone_saisi=TEL, nom_complet="Fatou"
    )
    await session.commit()
    lie = await comptes.lier_telegram(session, telephone_saisi="77 123 45 67", telegram_id=555)
    await session.commit()
    assert lie.id == cree.id
    assert lie.telegram_id == 555


@pytest.mark.integration
async def test_liaison_d_un_numero_inconnu(session: AsyncSession) -> None:
    with pytest.raises(CompteInexistant):
        await comptes.lier_telegram(session, telephone_saisi="+221770000000", telegram_id=555)


@pytest.mark.integration
async def test_liaison_idempotente(session: AsyncSession) -> None:
    await comptes.connecter_ou_inscrire(
        session, adresse=ADRESSE, telephone_saisi=TEL, nom_complet="Fatou"
    )
    await session.commit()
    await comptes.lier_telegram(session, telephone_saisi=TEL, telegram_id=555)
    await session.commit()
    encore = await comptes.lier_telegram(session, telephone_saisi=TEL, telegram_id=555)
    assert encore.telegram_id == 555


@pytest.mark.integration
async def test_revocation_incremente_la_version(session: AsyncSession) -> None:
    u = await comptes.connecter_ou_inscrire(
        session, adresse=ADRESSE, telephone_saisi=TEL, nom_complet="Fatou"
    )
    await session.commit()
    await comptes.revoquer_jetons(session, u)
    await session.commit()
    assert u.token_version == 1
```

- [ ] **Étape 2 : lancer le test et vérifier qu'il échoue**

Lancer : `pytest tests/test_auth_comptes.py -v`
Attendu : ÉCHEC, `ModuleNotFoundError: No module named 'src.core.auth.comptes'`

- [ ] **Étape 3 : écrire l'implémentation minimale**

Créer `src/core/auth/comptes.py` :

```python
"""Comptes utilisateurs (spec Phase 2 §8 et §9).

Deux règles portent tout le reste :

1. **Un seul endpoint pour l'inscription et la reconnexion.** C'est ce qui permet
   à `/auth/code/demande` de répondre exactement pareil que l'adresse existe ou
   non : sans cela, l'endpoint dirait publiquement qui est client.
2. **Un compte existant ignore les champs fournis.** Sinon `/auth/code/verifie`
   deviendrait un moyen d'écraser le numéro d'un compte — or ce numéro sert au
   paiement (§10) et à la liaison Telegram.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import courriel_valide, telephone
from src.core.erreurs import (
    CompteInexistant,
    InscriptionIncomplete,
    TelephoneDejaUtilise,
)
from src.db.models import User


async def par_adresse(session: AsyncSession, adresse: str) -> User | None:
    resultat = await session.execute(
        select(User).where(User.email == courriel_valide.normaliser(adresse))
    )
    return resultat.scalar_one_or_none()


async def par_telephone(session: AsyncSession, numero: str) -> User | None:
    resultat = await session.execute(
        select(User).where(User.phone == telephone.normaliser(numero))
    )
    return resultat.scalar_one_or_none()


async def par_telegram(session: AsyncSession, telegram_id: int) -> User | None:
    resultat = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return resultat.scalar_one_or_none()


async def connecter_ou_inscrire(
    session: AsyncSession,
    *,
    adresse: str,
    telephone_saisi: str | None = None,
    nom_complet: str | None = None,
) -> User:
    """Rend le compte existant, ou en crée un. L'adresse est déjà prouvée."""
    normalisee = courriel_valide.normaliser(adresse)

    existant = await par_adresse(session, normalisee)
    if existant is not None:
        return existant

    if not telephone_saisi or not nom_complet or not nom_complet.strip():
        raise InscriptionIncomplete(InscriptionIncomplete.code)

    numero = telephone.normaliser(telephone_saisi)
    if await par_telephone(session, numero) is not None:
        raise TelephoneDejaUtilise(TelephoneDejaUtilise.code)

    utilisateur = User(
        email=normalisee, phone=numero, full_name=nom_complet.strip(), state="onboarding"
    )
    session.add(utilisateur)
    await session.flush()
    return utilisateur


async def lier_telegram(session: AsyncSession, *, telephone_saisi: str, telegram_id: int) -> User:
    """Rattache un identifiant Telegram au compte portant ce numéro.

    Le numéro vient du bouton natif « partager mon contact » : Telegram l'a déjà
    vérifié. L'appelant DOIT avoir contrôlé que le contact appartient bien à
    l'expéditeur (`ContactUsurpe`) — ce module ne voit pas le message.
    """
    utilisateur = await par_telephone(session, telephone_saisi)
    if utilisateur is None:
        raise CompteInexistant(CompteInexistant.code)
    utilisateur.telegram_id = telegram_id
    await session.flush()
    return utilisateur


async def revoquer_jetons(session: AsyncSession, utilisateur: User) -> None:
    """Invalide d'un coup tous les jetons émis pour ce compte (§5)."""
    utilisateur.token_version += 1
    await session.flush()
```

> **Attention au nom du paramètre :** il s'appelle `telephone_saisi` et non `telephone`, sinon
> il masquerait le module `src.core.telephone` importé juste au-dessus. Les tests de l'étape 1
> l'utilisent déjà sous ce nom.

- [ ] **Étape 4 : lancer les tests et vérifier qu'ils passent**

```bash
RUN_INTEGRATION_TESTS=1 pytest tests/test_auth_comptes.py -m integration -v
mypy src/core/
```

Attendu : tous les tests PASSENT.

- [ ] **Étape 5 : commiter**

```bash
git add src/core/auth/comptes.py tests/test_auth_comptes.py
git commit -m "feat(core): comptes, inscription unifiée et liaison Telegram"
```

---

## Tâche 10 : abstraction d'envoi d'email

**Fichiers :**
- Créer : `src/courriel/__init__.py`, `src/courriel/provider.py`, `src/courriel/console.py`
- Test : `tests/test_courriel_provider.py`

**Interfaces :**
- Consomme : `src.config.Settings`
- Produit :
  - `class FournisseurCourriel(Protocol)` — `async envoyer_code(self, destinataire: str, code: str) -> None`
  - `class CourrielConsole` — implémentation qui journalise
  - `construire_fournisseur(settings: Settings) -> FournisseurCourriel`

> Même forme que `src/alerting.py` (`AlerteAdmin` / `AlerteJournalisee` / `construire_alerte`) et
> que `billing/provider.py` prévu au §10 : une interface, une fabrique pilotée par la config.
> Le nom du package est **`courriel`** et non `email` : `email` est un module de la bibliothèque
> standard, et le masquer est un piège d'import classique.

- [ ] **Étape 1 : écrire le test qui échoue**

Créer `tests/test_courriel_provider.py` :

```python
"""Envoi du code (spec Phase 2 §7)."""

from __future__ import annotations

import pytest
import structlog

from src.config import get_settings
from src.courriel.console import CourrielConsole
from src.courriel.provider import construire_fournisseur


@pytest.fixture
def journal() -> list[dict[str, object]]:
    captures: list[dict[str, object]] = []
    structlog.configure(processors=[structlog.testing.LogCapture(captures)])
    return captures


async def test_le_fournisseur_console_journalise_le_code(
    journal: list[dict[str, object]],
) -> None:
    await CourrielConsole().envoyer_code("fatou@example.sn", "123456")
    assert any(e.get("code") == "123456" for e in journal)
    assert any(e.get("destinataire") == "fatou@example.sn" for e in journal)


async def test_le_fournisseur_console_previent_qu_il_n_envoie_rien(
    journal: list[dict[str, object]],
) -> None:
    """Personne ne doit croire qu'un email est parti (CLAUDE.md §7)."""
    await CourrielConsole().envoyer_code("fatou@example.sn", "123456")
    assert any(e.get("event") == "courriel_non_envoye_mode_console" for e in journal)


def test_console_est_le_defaut() -> None:
    assert isinstance(construire_fournisseur(get_settings()), CourrielConsole)


def test_fournisseur_inconnu_refuse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un nom mal orthographié ne doit pas retomber silencieusement sur console."""
    monkeypatch.setenv("FOURNISSEUR_COURRIEL", "resendd")
    get_settings.cache_clear()
    with pytest.raises(ValueError):
        construire_fournisseur(get_settings())
```

- [ ] **Étape 2 : lancer le test et vérifier qu'il échoue**

Lancer : `pytest tests/test_courriel_provider.py -v`
Attendu : ÉCHEC, `ModuleNotFoundError: No module named 'src.courriel'`

- [ ] **Étape 3 : écrire l'implémentation minimale**

Créer `src/courriel/__init__.py` :

```python
"""Envoi d'email transactionnel.

Nommé `courriel` et NON `email` : `email` est un module de la bibliothèque
standard Python, et le masquer casse des imports à distance.
"""
```

Créer `src/courriel/provider.py` :

```python
"""Interface d'envoi et fabrique (spec Phase 2 §7).

Même forme que `src/alerting.py` : le métier ne connaît que l'interface, et le
fournisseur réel se branche sans toucher à un seul appelant.

Aucun fournisseur réel n'existe en Phase 2 : SPF, DKIM et DMARC exigent un
domaine possédé, encore à acheter (CLAUDE.md §14.1).
"""

from __future__ import annotations

from typing import Protocol

from src.config import Settings
from src.courriel.console import CourrielConsole


class FournisseurCourriel(Protocol):
    """Canal d'envoi du code de vérification."""

    async def envoyer_code(self, destinataire: str, code: str) -> None:
        """Transmet le code à l'adresse indiquée."""
        ...


def construire_fournisseur(settings: Settings) -> FournisseurCourriel:
    """Fournisseur à utiliser, selon la configuration."""
    if settings.fournisseur_courriel == "console":
        return CourrielConsole()
    # Pas de repli silencieux : une faute de frappe dans la variable
    # d'environnement enverrait les codes dans les logs en production.
    raise ValueError(
        f"FOURNISSEUR_COURRIEL inconnu : {settings.fournisseur_courriel!r}. "
        "Valeurs acceptées : console."
    )
```

Créer `src/courriel/console.py` :

```python
"""Fournisseur de développement : le code part dans les logs.

ATTENTION — c'est le SEUL endroit du projet où un code de vérification a le
droit d'être journalisé (CLAUDE.md §2, interdiction n°2). Ne jamais copier ce
motif ailleurs, et ne jamais activer ce fournisseur en production : quiconque
lit les logs peut ouvrir n'importe quelle session.
"""

from __future__ import annotations

from src.logging_setup import get_logger

log = get_logger(__name__)


class CourrielConsole:
    """Écrit le code au lieu de l'envoyer."""

    async def envoyer_code(self, destinataire: str, code: str) -> None:
        log.warning(
            "courriel_non_envoye_mode_console",
            destinataire=destinataire,
            code=code,
            rappel="Aucun email n'a été envoyé. Voir CLAUDE.md §14.1 (nom de domaine).",
        )
```

- [ ] **Étape 4 : lancer les tests et vérifier qu'ils passent**

Lancer : `pytest tests/test_courriel_provider.py -v && mypy src/courriel/`
Attendu : tous les tests PASSENT.

- [ ] **Étape 5 : commiter**

```bash
git add src/courriel/ tests/test_courriel_provider.py
git commit -m "feat(courriel): abstraction d'envoi et implémentation console"
```

---

## Tâche 11 : socle de l'API

**Fichiers :**
- Créer : `src/api/__init__.py`, `src/api/app.py`, `src/api/deps.py`, `src/api/main.py`,
  `src/api/routers/__init__.py`, `src/api/routers/sante.py`, `src/api/schemas/__init__.py`
- Supprimer : `src/health.py`
- Modifier : `src/bot/main.py` (retirer `_run_http`)
- Test : `tests/test_api_sante.py`

**Interfaces :**
- Consomme : `src.core.erreurs.ErreurMetier`, `src.db.session.get_engine`
- Produit :
  - `src.api.app.create_app() -> FastAPI`
  - `src.api.deps.session_db() -> AsyncIterator[AsyncSession]`
  - `src.api.deps.cache_redis() -> AsyncIterator[Redis]`
  - Gestionnaire d'exceptions : toute `ErreurMetier` devient
    `{"erreur": "<code>"}` avec le statut HTTP associé.

- [ ] **Étape 1 : écrire le test qui échoue**

Créer `tests/test_api_sante.py` :

```python
"""Socle de l'API : /health et traduction des erreurs métier."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.erreurs import CodeInvalide, PlafondGlobalAtteint, TropDeDemandes


def test_health_repond() -> None:
    """Postgres et Redis sont absents en test : /health répond 503, pas 500."""
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        reponse = client.get("/health")
    assert reponse.status_code in (200, 503)
    assert "checks" in reponse.json()


def test_erreur_metier_traduite_en_http() -> None:
    app = create_app()
    router = APIRouter()

    @router.get("/essai/invalide")
    async def invalide() -> None:
        raise CodeInvalide(CodeInvalide.code)

    @router.get("/essai/trop")
    async def trop() -> None:
        raise TropDeDemandes(attendre_secondes=60)

    @router.get("/essai/plafond")
    async def plafond() -> None:
        raise PlafondGlobalAtteint(PlafondGlobalAtteint.code)

    app.include_router(router)
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get("/essai/invalide")
        assert r.status_code == 400
        assert r.json() == {"erreur": "code_invalide"}

        r = client.get("/essai/trop")
        assert r.status_code == 429
        assert r.json()["erreur"] == "trop_de_demandes"
        assert r.headers["Retry-After"] == "60"

        r = client.get("/essai/plafond")
        assert r.status_code == 503


def test_documentation_desactivee() -> None:
    """Pas de /docs public : ça expose la surface d'attaque sans rien apporter ici."""
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
```

- [ ] **Étape 2 : lancer le test et vérifier qu'il échoue**

Lancer : `pytest tests/test_api_sante.py -v`
Attendu : ÉCHEC, `ModuleNotFoundError: No module named 'src.api'`

- [ ] **Étape 3 : écrire l'implémentation minimale**

Créer `src/api/__init__.py`, `src/api/routers/__init__.py`, `src/api/schemas/__init__.py`, chacun
avec une docstring d'une ligne (`"""Routers de l'API."""`, etc.).

Créer `src/api/routers/sante.py` — c'est l'ancien `src/health.py`, transposé en router :

```python
"""Healthcheck : Postgres + Redis. Déplacé depuis `src/health.py` le 2026-09-11,
quand le process `api` a remplacé le serveur HTTP monté dans le bot (CLAUDE.md §4).
"""

from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from src.config import get_settings
from src.db.session import get_engine
from src.logging_setup import get_logger

log = get_logger(__name__)
router = APIRouter(tags=["sante"])


@router.get("/health")
async def health(response: Response) -> dict[str, Any]:
    """Vérifie Postgres et Redis. 503 si l'un des deux est indisponible."""
    checks: dict[str, str] = {}

    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001 — le healthcheck ne doit jamais lever
        checks["postgres"] = "erreur"
        log.warning("healthcheck_postgres_ko", error=str(exc))

    client = aioredis.from_url(get_settings().redis_url)
    try:
        await client.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = "erreur"
        log.warning("healthcheck_redis_ko", error=str(exc))
    finally:
        await client.aclose()

    healthy = all(v == "ok" for v in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if healthy else "degraded", "checks": checks}
```

Créer `src/api/deps.py` :

```python
"""Dépendances FastAPI : session de base et client Redis."""

from __future__ import annotations

from collections.abc import AsyncIterator

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.db.session import session_scope


async def session_db() -> AsyncIterator[AsyncSession]:
    """Session transactionnelle : commit en sortie normale, rollback sur exception."""
    async with session_scope() as session:
        yield session


async def cache_redis() -> AsyncIterator[aioredis.Redis]:
    """Client Redis fermé en fin de requête."""
    client: aioredis.Redis = aioredis.from_url(
        get_settings().redis_url, decode_responses=True
    )
    try:
        yield client
    finally:
        await client.aclose()
```

Créer `src/api/app.py` :

```python
"""Construction de l'application FastAPI (CLAUDE.md §4).

L'API ne fait que traduire `src/core/` en HTTP. Les erreurs métier y arrivent
sous forme d'exceptions et en ressortent sous forme de **codes stables** — jamais
de phrases : les textes destinés à l'utilisateur vivent chez chaque client (§4).
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.api.routers import sante
from src.core.erreurs import (
    AdresseInvalide,
    CompteInexistant,
    ErreurMetier,
    InscriptionIncomplete,
    JetonInvalide,
    NumeroInvalide,
    PlafondGlobalAtteint,
    TelephoneDejaUtilise,
    TropDeDemandes,
)

# Chaque erreur métier a un statut HTTP, et un seul. Le défaut est 400 :
# une erreur non listée est une faute de saisie, pas une panne serveur.
_STATUTS: dict[type[ErreurMetier], int] = {
    AdresseInvalide: status.HTTP_422_UNPROCESSABLE_ENTITY,
    NumeroInvalide: status.HTTP_422_UNPROCESSABLE_ENTITY,
    InscriptionIncomplete: status.HTTP_422_UNPROCESSABLE_ENTITY,
    TelephoneDejaUtilise: status.HTTP_409_CONFLICT,
    TropDeDemandes: status.HTTP_429_TOO_MANY_REQUESTS,
    PlafondGlobalAtteint: status.HTTP_503_SERVICE_UNAVAILABLE,
    JetonInvalide: status.HTTP_401_UNAUTHORIZED,
    CompteInexistant: status.HTTP_404_NOT_FOUND,
}


def create_app() -> FastAPI:
    # docs/redoc/openapi désactivés : surface d'attaque inutile ici, les seuls
    # clients de cette API sont écrits dans ce même dépôt.
    app = FastAPI(title="JobBot", docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(ErreurMetier)
    async def _erreur_metier(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, ErreurMetier)
        code_http = _STATUTS.get(type(exc), status.HTTP_400_BAD_REQUEST)
        entetes = {}
        if isinstance(exc, TropDeDemandes):
            entetes["Retry-After"] = str(exc.attendre_secondes)
        return JSONResponse(
            status_code=code_http, content={"erreur": exc.code}, headers=entetes
        )

    app.include_router(sante.router)
    return app
```

Créer `src/api/main.py` :

```python
"""Entrypoint du process `api` (CLAUDE.md §4)."""

from __future__ import annotations

import asyncio
import contextlib

import uvicorn

from src.api.app import create_app
from src.config import get_settings
from src.db.session import dispose_engine
from src.logging_setup import get_logger, setup_logging

log = get_logger(__name__)


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, json_output=settings.is_prod)
    log.info(
        "demarrage_api",
        environment=settings.environment,
        http_port=settings.http_port,
        fournisseur_courriel=settings.fournisseur_courriel,
    )
    config = uvicorn.Config(
        create_app(),
        host=settings.http_host,
        port=settings.http_port,
        log_config=None,  # structlog gère déjà les logs
        access_log=False,
    )
    try:
        await uvicorn.Server(config).serve()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
```

- [ ] **Étape 4 : retirer le serveur HTTP du bot**

Dans `src/bot/main.py` : supprimer l'import `uvicorn`, l'import
`from src.health import create_app`, la fonction `_run_http`, et la tâche `http_task`. Dans
`main()`, remplacer le bloc `asyncio.wait({http_task, telegram_task}, ...)` par un simple
`await telegram_task`, en gardant le `try/except TelegramUnauthorizedError` et le `finally`.
Retirer `http_port=settings.http_port` du `log.info("demarrage_bot", ...)`.

Puis supprimer l'ancien fichier :

```bash
git rm src/health.py
```

- [ ] **Étape 5 : lancer les tests et vérifier qu'ils passent**

Lancer : `pytest tests/test_api_sante.py tests/test_bot_start.py tests/test_structure.py -v && mypy src/`
Attendu : tous les tests PASSENT.

> `tests/test_structure.py` référence peut-être `src/health.py` : si un test échoue à cause du
> fichier supprimé, **mettre le test à jour** pour attendre `src/api/routers/sante.py`.

- [ ] **Étape 6 : commiter**

```bash
git add -A src/api src/bot/main.py tests/test_api_sante.py tests/test_structure.py
git rm --cached src/health.py 2>/dev/null || true
git commit -m "feat(api): socle FastAPI, healthcheck déplacé, bot sans serveur HTTP"
```

---

## Tâche 12 : `/auth/code/demande`

**Fichiers :**
- Créer : `src/api/schemas/auth.py`, `src/api/routers/auth.py`
- Modifier : `src/api/app.py` (inclure le router)
- Test : `tests/test_api_auth_demande.py`

**Interfaces :**
- Consomme : `codes.generer_code`, `codes.deposer`, `limites.autoriser_envoi`,
  `courriel_valide.normaliser`, `construire_fournisseur`, `construire_alerte`
- Produit : `POST /auth/code/demande` — corps `{"email": str}`, réponse `202` et corps vide

> **Règle de conception n°1 de la spec :** cet endpoint répond **exactement pareil** que
> l'adresse existe ou non. Il ne touche donc jamais la base — il n'a aucune raison de le faire,
> et la tentation d'y ajouter un « si le compte existe… » est exactement ce qu'il faut éviter.

- [ ] **Étape 1 : écrire le test qui échoue**

Créer `tests/test_api_auth_demande.py` :

```python
"""POST /auth/code/demande (spec Phase 2 §8)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api import deps
from src.api.app import create_app
from tests.conftest import FauxCache


class FournisseurEspion:
    def __init__(self) -> None:
        self.envois: list[tuple[str, str]] = []

    async def envoyer_code(self, destinataire: str, code: str) -> None:
        self.envois.append((destinataire, code))


@pytest.fixture
def espion() -> FournisseurEspion:
    return FournisseurEspion()


@pytest.fixture
def client(espion: FournisseurEspion, faux_cache: FauxCache) -> Iterator[TestClient]:
    from src.api.routers import auth

    app = create_app()

    async def _cache() -> Any:
        yield faux_cache

    app.dependency_overrides[deps.cache_redis] = _cache
    app.dependency_overrides[auth.fournisseur] = lambda: espion
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_demande_acceptee(client: TestClient, espion: FournisseurEspion) -> None:
    reponse = client.post("/auth/code/demande", json={"email": "fatou@example.sn"})
    assert reponse.status_code == 202
    assert len(espion.envois) == 1
    destinataire, code = espion.envois[0]
    assert destinataire == "fatou@example.sn"
    assert len(code) == 6 and code.isdigit()


def test_adresse_normalisee_avant_envoi(client: TestClient, espion: FournisseurEspion) -> None:
    client.post("/auth/code/demande", json={"email": "  Fatou@EXAMPLE.SN "})
    assert espion.envois[0][0] == "Fatou@example.sn"


def test_adresse_invalide_refusee(client: TestClient, espion: FournisseurEspion) -> None:
    reponse = client.post("/auth/code/demande", json={"email": "pas-une-adresse"})
    assert reponse.status_code == 422
    assert reponse.json()["erreur"] == "adresse_invalide"
    assert espion.envois == []


def test_reponse_identique_pour_adresse_connue_ou_non(client: TestClient) -> None:
    """Sinon l'endpoint dit publiquement qui est client (spec §8, règle n°1)."""
    a = client.post("/auth/code/demande", json={"email": "connue@example.sn"})
    b = client.post("/auth/code/demande", json={"email": "jamais.vue@example.sn"})
    assert (a.status_code, a.text) == (b.status_code, b.text)


def test_cooldown_applique(client: TestClient) -> None:
    client.post("/auth/code/demande", json={"email": "fatou@example.sn"})
    seconde = client.post("/auth/code/demande", json={"email": "fatou@example.sn"})
    assert seconde.status_code == 429
    assert seconde.headers["Retry-After"] == "60"


def test_le_code_n_est_jamais_dans_la_reponse(client: TestClient) -> None:
    reponse = client.post("/auth/code/demande", json={"email": "fatou@example.sn"})
    assert reponse.text.strip() in ("", "null")
```

- [ ] **Étape 2 : lancer le test et vérifier qu'il échoue**

Lancer : `pytest tests/test_api_auth_demande.py -v`
Attendu : ÉCHEC, `ImportError: cannot import name 'auth' from 'src.api.routers'`

- [ ] **Étape 3 : écrire l'implémentation minimale**

Créer `src/api/schemas/auth.py` :

```python
"""Entrées et sorties de l'authentification.

`EmailStr` de pydantic n'est PAS utilisé : la validation et la normalisation
vivent dans `src/core/courriel_valide.py`, pour que le bot et l'API appliquent
exactement la même règle.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DemandeCode(BaseModel):
    email: str = Field(min_length=1, max_length=320)


class VerificationCode(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    code: str = Field(min_length=1, max_length=12)
    telephone: str | None = Field(default=None, max_length=32)
    nom_complet: str | None = Field(default=None, max_length=255)


class Utilisateur(BaseModel):
    """Ce qu'un client a le droit de savoir d'un compte.

    Volontairement restreint : `token_version` et les identifiants internes
    n'ont aucune raison de sortir.
    """

    id: int
    email: str
    telephone: str
    nom_complet: str | None
    telegram_lie: bool
    etat: str

    @classmethod
    def depuis(cls, utilisateur: Any) -> Utilisateur:
        """Projette une ligne `users`. Ici plutôt que dans un router : deux
        routers en ont besoin, et importer une fonction privée d'un router
        depuis un autre recouplerait les deux."""
        return cls(
            id=utilisateur.id,
            email=utilisateur.email,
            telephone=utilisateur.phone,
            nom_complet=utilisateur.full_name,
            telegram_lie=utilisateur.telegram_id is not None,
            etat=utilisateur.state,
        )
```

L'import du haut du fichier devient :

```python
from typing import Any

from pydantic import BaseModel, Field
```

Créer `src/api/routers/auth.py` :

```python
"""Authentification par email + code à 6 chiffres (spec Phase 2 §8).

`/auth/code/demande` ne consulte JAMAIS la base : il doit répondre exactement
pareil que l'adresse existe ou non, sinon il devient un annuaire public de la
clientèle. Toute la logique « ce compte existe-t-il ? » vit dans
`/auth/code/verifie`, derrière la preuve de possession de l'adresse.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from src.alerting import AlerteAdmin, construire_alerte
from src.api import deps
from src.api.schemas.auth import DemandeCode
from src.config import Settings, get_settings
from src.core import courriel_valide
from src.core.auth import codes
from src.core.auth.limites import ReglesEnvoi, autoriser_envoi
from src.core.cache import CacheRedis
from src.courriel.provider import FournisseurCourriel, construire_fournisseur
from src.logging_setup import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def reglages() -> Settings:
    return get_settings()


def fournisseur(
    settings: Annotated[Settings, Depends(reglages)],
) -> FournisseurCourriel:
    """Surchargeable dans les tests, pour ne jamais rien envoyer."""
    return construire_fournisseur(settings)


def alerte(settings: Annotated[Settings, Depends(reglages)]) -> AlerteAdmin:
    return construire_alerte(settings)


def _regles(settings: Settings) -> ReglesEnvoi:
    return ReglesEnvoi(
        cooldown_secondes=settings.auth_cooldown_secondes,
        par_heure=settings.auth_envois_par_heure,
        par_jour=settings.auth_envois_par_jour,
        par_ip_heure=settings.auth_envois_par_ip_heure,
        plafond_global_jour=settings.auth_plafond_global_jour,
    )


@router.post("/code/demande", status_code=status.HTTP_202_ACCEPTED)
async def demander_code(
    corps: DemandeCode,
    request: Request,
    response: Response,
    cache: Annotated[CacheRedis, Depends(deps.cache_redis)],
    settings: Annotated[Settings, Depends(reglages)],
    envoi: Annotated[FournisseurCourriel, Depends(fournisseur)],
    canal_alerte: Annotated[AlerteAdmin, Depends(alerte)],
) -> None:
    """Envoie un code. Réponse identique que l'adresse existe ou non."""
    adresse = courriel_valide.normaliser(corps.email)
    ip = request.client.host if request.client else "inconnue"

    await autoriser_envoi(
        cache,
        adresse=adresse,
        ip=ip,
        regles=_regles(settings),
        secret=settings.jwt_secret.get_secret_value(),
        alerte=canal_alerte,
    )

    code = codes.generer_code()
    await codes.deposer(
        cache,
        adresse,
        code,
        secret=settings.jwt_secret.get_secret_value(),
        ttl_secondes=settings.code_ttl_secondes,
    )
    await envoi.envoyer_code(adresse, code)

    # Jamais le code, jamais l'adresse en clair : ce log sert au suivi des
    # abandons d'onboarding (§11), pas au débogage d'un compte.
    log.info("code_demande", domaine=adresse.rsplit("@", 1)[-1])
    response.status_code = status.HTTP_202_ACCEPTED
```

Dans `src/api/app.py`, ajouter l'import `from src.api.routers import auth, sante` et, après
`app.include_router(sante.router)` :

```python
    app.include_router(auth.router)
```

- [ ] **Étape 4 : lancer les tests et vérifier qu'ils passent**

Lancer : `pytest tests/test_api_auth_demande.py -v && mypy src/`
Attendu : tous les tests PASSENT.

- [ ] **Étape 5 : commiter**

```bash
git add src/api tests/test_api_auth_demande.py
git commit -m "feat(api): POST /auth/code/demande, sans énumération de comptes"
```

---

## Tâche 13 : `/auth/code/verifie`

**Fichiers :**
- Modifier : `src/api/routers/auth.py`
- Test : `tests/test_api_auth_verifie.py`

**Interfaces :**
- Consomme : `codes.verifier`, `comptes.connecter_ou_inscrire`, `jetons.encoder`
- Produit : `POST /auth/code/verifie` — corps `VerificationCode`, réponse `200` avec un
  `Utilisateur` et le cookie de session ; `422 {"erreur": "inscription_incomplete"}` quand le
  compte est nouveau et que nom/téléphone manquent, **sans consommer le code**.

> **Point délicat, à ne pas rater :** en cas d'`InscriptionIncomplete`, le code de vérification
> doit **rester valable**, pour que le client affiche le formulaire complémentaire sans renvoyer
> d'email. Or `codes.verifier` consomme le code en cas de succès. L'ordre est donc : vérifier le
> code → si le compte est incomplet, **redéposer le même code** avant de lever.

- [ ] **Étape 1 : écrire le test qui échoue**

Créer `tests/test_api_auth_verifie.py` :

```python
"""POST /auth/code/verifie (spec Phase 2 §8).

Lancer avec : RUN_INTEGRATION_TESTS=1 pytest -m integration
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.api import deps
from src.api.app import create_app
from src.config import get_settings
from src.core.auth import jetons
from src.db.models import User
from tests.conftest import FauxCache

ADRESSE = "fatou@jobbot-test.sn"
TEL = "+221771234567"


class FournisseurEspion:
    def __init__(self) -> None:
        self.envois: list[tuple[str, str]] = []

    async def envoyer_code(self, destinataire: str, code: str) -> None:
        self.envois.append((destinataire, code))


@pytest_asyncio.fixture
async def base(postgres_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    moteur = create_async_engine(postgres_url)
    fabrique = async_sessionmaker(moteur, expire_on_commit=False)
    async with fabrique() as s:
        await s.execute(delete(User).where(User.email.like("%@jobbot-test.sn")))
        await s.commit()
    yield fabrique
    async with fabrique() as s:
        await s.execute(delete(User).where(User.email.like("%@jobbot-test.sn")))
        await s.commit()
    await moteur.dispose()


@pytest.fixture
def espion() -> FournisseurEspion:
    return FournisseurEspion()


@pytest.fixture
def client(
    espion: FournisseurEspion,
    faux_cache: FauxCache,
    base: async_sessionmaker[AsyncSession],
) -> Iterator[TestClient]:
    from src.api.routers import auth

    app = create_app()

    async def _cache() -> Any:
        yield faux_cache

    async def _session() -> Any:
        async with base() as session:
            yield session
            await session.commit()

    app.dependency_overrides[deps.cache_redis] = _cache
    app.dependency_overrides[deps.session_db] = _session
    app.dependency_overrides[auth.fournisseur] = lambda: espion
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _code(client: TestClient, espion: FournisseurEspion, adresse: str = ADRESSE) -> str:
    client.post("/auth/code/demande", json={"email": adresse})
    return espion.envois[-1][1]


@pytest.mark.integration
def test_inscription_complete(client: TestClient, espion: FournisseurEspion) -> None:
    code = _code(client, espion)
    r = client.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "telephone": "77 123 45 67",
              "nom_complet": "Fatou Diop"},
    )
    assert r.status_code == 200
    corps = r.json()
    assert corps["email"] == ADRESSE
    assert corps["telephone"] == TEL
    assert corps["telegram_lie"] is False
    assert get_settings().cookie_session_nom in r.cookies


@pytest.mark.integration
def test_le_cookie_est_httponly(client: TestClient, espion: FournisseurEspion) -> None:
    """Un cookie lisible en JS est volable par n'importe quelle faille XSS."""
    code = _code(client, espion)
    r = client.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "telephone": TEL, "nom_complet": "Fatou"},
    )
    entete = r.headers["set-cookie"].lower()
    assert "httponly" in entete
    assert "samesite=lax" in entete


@pytest.mark.integration
def test_le_jeton_porte_le_compte(client: TestClient, espion: FournisseurEspion) -> None:
    code = _code(client, espion)
    r = client.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "telephone": TEL, "nom_complet": "Fatou"},
    )
    jeton = r.cookies[get_settings().cookie_session_nom]
    revendications = jetons.decoder(jeton, secret=get_settings().jwt_secret.get_secret_value())
    assert revendications.user_id == r.json()["id"]
    assert revendications.token_version == 0


@pytest.mark.integration
def test_compte_nouveau_sans_telephone(client: TestClient, espion: FournisseurEspion) -> None:
    code = _code(client, espion)
    r = client.post("/auth/code/verifie", json={"email": ADRESSE, "code": code})
    assert r.status_code == 422
    assert r.json()["erreur"] == "inscription_incomplete"


@pytest.mark.integration
def test_le_code_survit_a_une_inscription_incomplete(
    client: TestClient, espion: FournisseurEspion
) -> None:
    """Sinon l'utilisateur doit redemander un email pour saisir son nom."""
    code = _code(client, espion)
    client.post("/auth/code/verifie", json={"email": ADRESSE, "code": code})
    r = client.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "telephone": TEL, "nom_complet": "Fatou"},
    )
    assert r.status_code == 200
    assert len(espion.envois) == 1  # aucun second email


@pytest.mark.integration
def test_reconnexion_sans_ressaisir(client: TestClient, espion: FournisseurEspion) -> None:
    code = _code(client, espion)
    client.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "telephone": TEL, "nom_complet": "Fatou"},
    )
    code2 = _code(client, espion)
    r = client.post("/auth/code/verifie", json={"email": ADRESSE, "code": code2})
    assert r.status_code == 200
    assert r.json()["telephone"] == TEL


@pytest.mark.integration
def test_mauvais_code(client: TestClient, espion: FournisseurEspion) -> None:
    _code(client, espion)
    r = client.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": "000000", "telephone": TEL, "nom_complet": "F"},
    )
    assert r.status_code == 400
    assert r.json()["erreur"] == "code_invalide"


@pytest.mark.integration
def test_code_jamais_demande(client: TestClient) -> None:
    r = client.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": "123456", "telephone": TEL, "nom_complet": "F"},
    )
    assert r.status_code == 400
    assert r.json()["erreur"] == "code_expire"


@pytest.mark.integration
def test_code_a_usage_unique(client: TestClient, espion: FournisseurEspion) -> None:
    code = _code(client, espion)
    client.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "telephone": TEL, "nom_complet": "Fatou"},
    )
    r = client.post("/auth/code/verifie", json={"email": ADRESSE, "code": code})
    assert r.status_code == 400
    assert r.json()["erreur"] == "code_expire"
```

- [ ] **Étape 2 : lancer le test et vérifier qu'il échoue**

Lancer : `RUN_INTEGRATION_TESTS=1 pytest tests/test_api_auth_verifie.py -m integration -v`
Attendu : ÉCHEC, `404` sur `/auth/code/verifie`

- [ ] **Étape 3 : écrire l'implémentation minimale**

Ajouter à `src/api/routers/auth.py` — imports :

```python
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.auth import DemandeCode, Utilisateur, VerificationCode
from src.core.auth import comptes, jetons
from src.core.erreurs import InscriptionIncomplete
from src.db.models import User
```

Puis, à la fin du fichier :

```python
def poser_cookie(response: Response, utilisateur: User, settings: Settings) -> None:
    """Dépose le jeton de session.

    `httponly` : un cookie lisible en JavaScript est volable par la moindre
    faille XSS. `samesite=lax` : suffisant puisque `web` et `api` partagent
    l'origine (§4). `secure` uniquement en production, où l'on est en HTTPS.
    """
    jeton = jetons.encoder(
        user_id=utilisateur.id,
        token_version=utilisateur.token_version,
        secret=settings.jwt_secret.get_secret_value(),
        duree_jours=settings.jwt_duree_jours,
    )
    response.set_cookie(
        settings.cookie_session_nom,
        jeton,
        max_age=settings.jwt_duree_jours * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_session_secure,
        path="/",
    )


@router.post("/code/verifie")
async def verifier_code(
    corps: VerificationCode,
    response: Response,
    session: Annotated[AsyncSession, Depends(deps.session_db)],
    cache: Annotated[CacheRedis, Depends(deps.cache_redis)],
    settings: Annotated[Settings, Depends(reglages)],
) -> Utilisateur:
    """Inscrit ou connecte. Un seul endpoint pour les deux cas (spec §8)."""
    secret = settings.jwt_secret.get_secret_value()
    adresse = courriel_valide.normaliser(corps.email)

    await codes.verifier(
        cache, adresse, corps.code, secret=secret, essais_max=settings.code_essais_max
    )

    try:
        utilisateur = await comptes.connecter_ou_inscrire(
            session,
            adresse=adresse,
            telephone_saisi=corps.telephone,
            nom_complet=corps.nom_complet,
        )
    except InscriptionIncomplete:
        # `verifier` a consommé le code. Le redéposer : sinon l'utilisateur
        # devrait redemander un email juste pour saisir son nom.
        await codes.deposer(
            cache, adresse, corps.code, secret=secret, ttl_secondes=settings.code_ttl_secondes
        )
        raise

    poser_cookie(response, utilisateur, settings)
    log.info("compte_connecte", user_id=utilisateur.id, etat=utilisateur.state)
    return Utilisateur.depuis(utilisateur)
```

- [ ] **Étape 4 : lancer les tests et vérifier qu'ils passent**

```bash
RUN_INTEGRATION_TESTS=1 pytest tests/test_api_auth_verifie.py -m integration -v
pytest tests/test_api_auth_demande.py -v
mypy src/
```

Attendu : tous les tests PASSENT.

- [ ] **Étape 5 : commiter**

```bash
git add src/api tests/test_api_auth_verifie.py
git commit -m "feat(api): POST /auth/code/verifie, inscription et reconnexion unifiées"
```

---

## Tâche 14 : compte courant, déconnexion, jeton de liaison

**Fichiers :**
- Créer : `src/api/routers/moi.py`
- Modifier : `src/api/deps.py` (dépendance `utilisateur_courant`), `src/api/app.py`,
  `src/api/routers/auth.py` (`POST /auth/deconnexion`)
- Test : `tests/test_api_moi.py`

**Interfaces :**
- Consomme : `jetons.decoder`, `comptes.revoquer_jetons`
- Produit :
  - `deps.utilisateur_courant(...) -> User` — lève `JetonInvalide` (401) si absent, expiré,
    altéré, ou si `token_version` ne correspond plus
  - `GET /moi -> Utilisateur`
  - `POST /auth/deconnexion -> 204` — incrémente `token_version` et efface le cookie
  - `POST /moi/telegram/jeton -> {"lien": str, "expire_dans": int}`

- [ ] **Étape 1 : écrire le test qui échoue**

Créer `tests/test_api_moi.py`, en réutilisant les fixtures `base`, `espion`, `client` et le
helper `_code` de `tests/test_api_auth_verifie.py` (les recopier à l'identique — ce fichier doit
pouvoir être lu seul) puis :

```python
@pytest.mark.integration
def test_moi_sans_cookie_refuse(client: TestClient) -> None:
    r = client.get("/moi")
    assert r.status_code == 401
    assert r.json()["erreur"] == "jeton_invalide"


@pytest.mark.integration
def test_moi_avec_cookie(client: TestClient, espion: FournisseurEspion) -> None:
    code = _code(client, espion)
    client.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "telephone": TEL, "nom_complet": "Fatou"},
    )
    r = client.get("/moi")
    assert r.status_code == 200
    assert r.json()["email"] == ADRESSE


@pytest.mark.integration
def test_jeton_bricole_refuse(client: TestClient, espion: FournisseurEspion) -> None:
    code = _code(client, espion)
    client.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "telephone": TEL, "nom_complet": "Fatou"},
    )
    client.cookies.set(get_settings().cookie_session_nom, "pas.un.jeton")
    assert client.get("/moi").status_code == 401


@pytest.mark.integration
def test_deconnexion_invalide_le_jeton(client: TestClient, espion: FournisseurEspion) -> None:
    """C'est tout l'intérêt de token_version : pas de table de sessions (spec §5)."""
    code = _code(client, espion)
    r = client.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "telephone": TEL, "nom_complet": "Fatou"},
    )
    jeton = r.cookies[get_settings().cookie_session_nom]
    assert client.post("/auth/deconnexion").status_code == 204

    # Même en rejouant le jeton d'origine, l'accès est refusé.
    client.cookies.set(get_settings().cookie_session_nom, jeton)
    assert client.get("/moi").status_code == 401


@pytest.mark.integration
def test_jeton_de_liaison_telegram(
    client: TestClient, espion: FournisseurEspion, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "jobbot_sn_bot")
    get_settings.cache_clear()
    code = _code(client, espion)
    client.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "telephone": TEL, "nom_complet": "Fatou"},
    )
    r = client.post("/moi/telegram/jeton")
    assert r.status_code == 200
    assert r.json()["lien"].startswith("https://t.me/jobbot_sn_bot?start=")
    assert r.json()["expire_dans"] == 600


@pytest.mark.integration
def test_jeton_de_liaison_exige_une_session(client: TestClient) -> None:
    assert client.post("/moi/telegram/jeton").status_code == 401
```

- [ ] **Étape 2 : lancer le test et vérifier qu'il échoue**

Lancer : `RUN_INTEGRATION_TESTS=1 pytest tests/test_api_moi.py -m integration -v`
Attendu : ÉCHEC, `404` sur `/moi`

- [ ] **Étape 3 : ajouter la dépendance d'authentification**

Ajouter à `src/api/deps.py`. **Fusionner** ces imports avec ceux déjà présents plutôt que de
les dupliquer — `AsyncSession` y est déjà, et `ruff` (règle `I`) impose l'ordre alphabétique par
groupe :

```python
# À fusionner avec les imports existants du fichier :
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select

from src.config import Settings, get_settings
from src.core.auth import jetons
from src.core.erreurs import JetonInvalide
from src.db.models import User


async def utilisateur_courant(
    request: Request,
    session: Annotated[AsyncSession, Depends(session_db)],
) -> User:
    """Compte de la session en cours, ou `JetonInvalide` (401).

    `token_version` est comparé à chaque requête : c'est ce qui remplace une
    table de sessions (spec Phase 2 §5). On charge déjà l'utilisateur, donc la
    vérification ne coûte aucune requête supplémentaire.
    """
    settings: Settings = get_settings()
    jeton = request.cookies.get(settings.cookie_session_nom)
    if not jeton:
        raise JetonInvalide(JetonInvalide.code)

    revendications = jetons.decoder(jeton, secret=settings.jwt_secret.get_secret_value())
    resultat = await session.execute(select(User).where(User.id == revendications.user_id))
    utilisateur = resultat.scalar_one_or_none()
    if utilisateur is None or utilisateur.token_version != revendications.token_version:
        raise JetonInvalide(JetonInvalide.code)
    return utilisateur
```

- [ ] **Étape 4 : écrire le router `moi`**

Créer `src/api/routers/moi.py` :

```python
"""Compte courant et liaison Telegram (spec Phase 2 §9)."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api import deps
from src.api.schemas.auth import Utilisateur
from src.config import Settings, get_settings
from src.core.cache import CacheRedis
from src.db.models import User

router = APIRouter(tags=["moi"])

# Assez long pour le partager par-dessus l'épaule, assez court pour ne pas
# traîner : le lien ouvre une session Telegram sur le compte.
LIAISON_TTL_SECONDES = 600
_PREFIXE_LIAISON = "jobbot:auth:liaison"


def reglages() -> Settings:
    return get_settings()


@router.get("/moi")
async def moi(
    utilisateur: Annotated[User, Depends(deps.utilisateur_courant)],
) -> Utilisateur:
    return Utilisateur.depuis(utilisateur)


@router.post("/moi/telegram/jeton")
async def jeton_de_liaison(
    utilisateur: Annotated[User, Depends(deps.utilisateur_courant)],
    cache: Annotated[CacheRedis, Depends(deps.cache_redis)],
    settings: Annotated[Settings, Depends(reglages)],
) -> dict[str, object]:
    """Lien profond de liaison, pour qui utilise Telegram avec un autre numéro.

    Repli du chemin normal, qui est le bouton natif « partager mon contact ».
    Jeton à usage unique : le bot le consomme à la première utilisation.
    """
    jeton = secrets.token_urlsafe(24)
    await cache.set(
        f"{_PREFIXE_LIAISON}:{jeton}", str(utilisateur.id), ex=LIAISON_TTL_SECONDES
    )
    return {
        "lien": f"https://t.me/{settings.telegram_bot_username}?start={jeton}",
        "expire_dans": LIAISON_TTL_SECONDES,
    }
```

- [ ] **Étape 5 : ajouter la déconnexion**

Ajouter à la fin de `src/api/routers/auth.py` (et compléter les imports avec
`from src.core.auth import codes, comptes, jetons` et `from sqlalchemy.ext.asyncio import AsyncSession`) :

```python
@router.post("/deconnexion", status_code=status.HTTP_204_NO_CONTENT)
async def deconnexion(
    response: Response,
    utilisateur: Annotated[User, Depends(deps.utilisateur_courant)],
    session: Annotated[AsyncSession, Depends(deps.session_db)],
    settings: Annotated[Settings, Depends(reglages)],
) -> None:
    """Invalide TOUS les jetons du compte, pas seulement celui-ci (spec §5)."""
    await comptes.revoquer_jetons(session, utilisateur)
    response.delete_cookie(settings.cookie_session_nom, path="/")
```

Dans `src/api/app.py`, ajouter `moi` à l'import des routers et
`app.include_router(moi.router)`.

- [ ] **Étape 6 : lancer les tests et vérifier qu'ils passent**

```bash
RUN_INTEGRATION_TESTS=1 pytest tests/test_api_moi.py tests/test_api_auth_verifie.py -m integration -v
pytest tests/test_api_sante.py tests/test_api_auth_demande.py -v
mypy src/
```

Attendu : tous les tests PASSENT.

- [ ] **Étape 7 : commiter**

```bash
git add src/api tests/test_api_moi.py
git commit -m "feat(api): /moi, déconnexion révocable et jeton de liaison Telegram"
```

---

## Tâche 15 : Docker Compose

**Fichiers :**
- Modifier : `docker-compose.yml`
- Test : `tests/test_compose.py`

**Interfaces :**
- Consomme : `src/api/main.py`
- Produit : service `api` exposant `HTTP_PORT` avec le healthcheck `/health` ; service `bot`
  sans port ni healthcheck HTTP.

> **Pourquoi le service `bot` perd son healthcheck** plutôt que d'en recevoir un autre : il ne
> sert plus de HTTP, et fabriquer un fichier de battement rien que pour Docker serait du code
> écrit pour l'outil, pas pour le produit (§2.5). `restart: unless-stopped` suffit, et une panne
> réelle du bot se voit dans les logs et par l'absence de réponse à `/start`.

- [ ] **Étape 1 : écrire le test qui échoue**

Créer `tests/test_compose.py` :

```python
"""Le fichier compose décrit bien les cinq processus du §4."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

yaml = pytest.importorskip("yaml")

COMPOSE: dict[str, Any] = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
SERVICES: dict[str, Any] = COMPOSE["services"]


def test_le_service_api_existe() -> None:
    assert SERVICES["api"]["command"] == ["python", "-m", "src.api.main"]


def test_l_api_expose_le_port_http() -> None:
    assert any("HTTP_PORT" in str(p) for p in SERVICES["api"]["ports"])


def test_l_api_porte_le_healthcheck() -> None:
    assert "health" in str(SERVICES["api"]["healthcheck"]["test"])


def test_le_bot_n_expose_plus_de_port() -> None:
    """Le bot ne sert plus de HTTP depuis le 2026-09-11 (CLAUDE.md §4)."""
    assert "ports" not in SERVICES["bot"]
    assert "healthcheck" not in SERVICES["bot"]


def test_les_cinq_processus_sont_declares() -> None:
    attendus = {"api", "web", "bot", "worker_ingest", "worker_match"}
    assert attendus <= set(SERVICES)


def test_postgres_reste_sur_la_boucle_locale() -> None:
    """Ne jamais exposer la base sur 0.0.0.0 (commentaire du fichier compose)."""
    assert all(str(p).startswith("127.0.0.1:") for p in SERVICES["postgres"]["ports"])
```

> Le service `web` est ajouté ici en **squelette commenté** ; son image est construite par le
> plan « client web ». Si `test_les_cinq_processus_sont_declares` gêne à ce stade, le service
> `web` doit tout de même figurer dans le fichier — c'est ce que vérifie le test.

- [ ] **Étape 2 : lancer le test et vérifier qu'il échoue**

Lancer : `pytest tests/test_compose.py -v`
Attendu : ÉCHEC, `KeyError: 'api'`

- [ ] **Étape 3 : modifier `docker-compose.yml`**

Ajouter le service `api` avant `bot` :

```yaml
  api:
    <<: *app
    command: ["python", "-m", "src.api.main"]
    ports:
      - "${HTTP_PORT:-8080}:${HTTP_PORT:-8080}"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      migrate:
        condition: service_completed_successfully
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,os,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('HTTP_PORT','8080')+'/health', timeout=5).status==200 else 1)"]
      interval: 15s
      timeout: 10s
      retries: 5
      start_period: 20s
```

Remplacer le service `bot` par (suppression du bloc `ports` et du bloc `healthcheck`) :

```yaml
  bot:
    <<: *app
    command: ["python", "-m", "src.bot.main"]
    # Plus de `ports` ni de `healthcheck` : depuis le 2026-09-11 le bot ne sert
    # plus de HTTP, c'est le service `api` qui porte /health (CLAUDE.md §4).
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      migrate:
        condition: service_completed_successfully
```

Ajouter le squelette du service `web` après `bot` :

```yaml
  # Client Next.js. L'image est construite par le plan « client web » ;
  # `web/Dockerfile` n'existe pas encore, donc ce service ne démarre pas tant
  # que ce plan n'est pas exécuté. Déclaré ici pour que l'architecture du §4
  # soit lisible dans un seul fichier.
  web:
    build:
      context: ./web
    env_file: .env
    depends_on:
      api:
        condition: service_healthy
    restart: unless-stopped
    profiles: ["web"]
```

> `profiles: ["web"]` est important : sans lui, `docker compose up` échouerait à construire une
> image dont le `Dockerfile` n'existe pas encore. Le service sera activé par
> `docker compose --profile web up` quand le plan client web sera exécuté.

- [ ] **Étape 4 : ajouter `pyyaml` aux dépendances de test**

Dans `pyproject.toml`, section `[project.optional-dependencies] dev`, ajouter :

```toml
    "pyyaml>=6.0",
```

Justification (§3) : lire `docker-compose.yml` dans un test plutôt que de vérifier
l'architecture à l'œil. Dépendance de **développement uniquement**, absente de l'image.

- [ ] **Étape 5 : lancer les tests et vérifier qu'ils passent**

```bash
pip install -e '.[dev]'
pytest tests/test_compose.py -v
docker compose build
docker compose up -d
docker compose ps
curl -s localhost:8080/health
```

Attendu : les tests PASSENT ; `api` démarre et `/health` répond `{"status": "ok", ...}`.

- [ ] **Étape 6 : commiter**

```bash
git add docker-compose.yml pyproject.toml tests/test_compose.py
git commit -m "feat(compose): service api, bot sans serveur HTTP, squelette web"
```

---

## Tâche 16 : liaison du compte depuis le bot

**Fichiers :**
- Créer : `src/bot/handlers/compte.py`
- Modifier : `src/bot/texts.py`, `src/bot/keyboards.py`, `src/bot/handlers/__init__.py`
- Test : `tests/test_bot_compte.py`, `tests/test_texts.py` (compléter)

**Interfaces :**
- Consomme : `comptes.lier_telegram`, `comptes.par_telegram`, `erreurs.ContactUsurpe`,
  `erreurs.CompteInexistant`
- Produit : `verifier_contact(contact, expediteur_id) -> str` (rend le numéro, lève
  `ContactUsurpe`) ; `router` aiogram gérant `F.contact`.

> **Deux choses dans cette tâche, et la seconde n'est pas cosmétique.** `texts.py` promet
> aujourd'hui « je postule pour vous » dans `START` et « je peux postuler à votre place » dans
> `AIDE`. C'est contraire au §2 depuis le 2026-09-08 ; seule la documentation avait été corrigée
> par le commit `c920cb7`. C'est la promesse faite à l'utilisateur au tout premier écran.

- [ ] **Étape 1 : écrire le test qui échoue**

Créer `tests/test_bot_compte.py` :

```python
"""Liaison de compte par « partager mon contact » (spec Phase 2 §9)."""

from __future__ import annotations

import pytest

from src.bot.handlers.compte import verifier_contact
from src.core.erreurs import ContactUsurpe


class FauxContact:
    def __init__(self, phone_number: str, user_id: int | None) -> None:
        self.phone_number = phone_number
        self.user_id = user_id


def test_contact_personnel_accepte() -> None:
    assert verifier_contact(FauxContact("+221771234567", 555), 555) == "+221771234567"


def test_contact_d_un_tiers_refuse() -> None:
    """Sans ce contrôle, on se greffe sur le compte de quelqu'un d'autre."""
    with pytest.raises(ContactUsurpe):
        verifier_contact(FauxContact("+221779999999", 999), 555)


def test_contact_sans_user_id_refuse() -> None:
    """Un contact saisi à la main n'a pas de user_id : rien ne le vérifie."""
    with pytest.raises(ContactUsurpe):
        verifier_contact(FauxContact("+221771234567", None), 555)
```

Ajouter à `tests/test_texts.py` :

```python
def test_aucun_texte_ne_promet_de_postuler() -> None:
    """CLAUDE.md §2, interdiction n°1 : le bot prépare, l'utilisateur dépose."""
    from src.bot import texts

    interdits = ("postule pour vous", "postuler à votre place", "je postule", "j'envoie")
    for nom in dir(texts):
        if nom.startswith("_"):
            continue
        valeur = getattr(texts, nom)
        if not isinstance(valeur, str):
            continue
        minuscule = valeur.lower()
        for motif in interdits:
            assert motif not in minuscule, f"{nom} promet un envoi : {motif!r}"
```

- [ ] **Étape 2 : lancer les tests et vérifier qu'ils échouent**

Lancer : `pytest tests/test_bot_compte.py tests/test_texts.py -v`
Attendu : ÉCHEC — `ModuleNotFoundError` pour `compte`, et
`AssertionError: START promet un envoi : 'postule pour vous'`

- [ ] **Étape 3 : corriger les textes**

Dans `src/bot/texts.py`, remplacer `START` et `AIDE`, et ajouter les textes de liaison :

```python
START: Final = (
    "Bonjour {prenom} 👋\n"
    "Je trouve les offres d'emploi qui vous correspondent au Sénégal, "
    "et je prépare votre CV et votre lettre pour chacune.\n"
    "C'est vous qui déposez votre candidature — je vous dis où et comment."
)

AIDE: Final = (
    "*Comment ça marche*\n"
    "1. Vous créez votre compte avec votre adresse email.\n"
    "2. Vous envoyez votre CV (PDF ou Word).\n"
    "3. Vous vérifiez ce que j'ai compris de votre parcours.\n"
    "4. Vous recevez des offres, avec un CV et une lettre prêts à déposer.\n\n"
    "Je ne postule jamais à votre place : je prépare tout, vous envoyez.\n\n"
    "*Commandes*\n"
    "/start — revenir au début\n"
    "/compte — lier ce Telegram à votre compte\n"
    "/aide — afficher ce message\n\n"
    "Un souci ? Répondez simplement à ce message."
)

# --- Liaison de compte ------------------------------------------------------

COMPTE_DEMANDER_CONTACT: Final = (
    "Pour retrouver votre compte, appuyez sur le bouton ci-dessous.\n"
    "Telegram me transmettra votre numéro, rien d'autre."
)

COMPTE_LIE: Final = (
    "C'est fait, ce Telegram est relié à votre compte.\n"
    "Vous recevrez ici les offres qui vous correspondent."
)

COMPTE_DEJA_LIE: Final = "Ce Telegram est déjà relié à votre compte."

COMPTE_INTROUVABLE: Final = (
    "Je ne trouve aucun compte avec ce numéro.\n"
    "Créez d'abord votre compte, puis revenez ici."
)

COMPTE_CONTACT_REFUSE: Final = (
    "Ce contact n'est pas le vôtre. Utilisez le bouton pour partager votre propre numéro."
)

BTN_PARTAGER_CONTACT: Final = "📱 Partager mon numéro"
```

- [ ] **Étape 4 : ajouter le clavier**

Ajouter à `src/bot/keyboards.py` :

```python
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def partager_contact() -> ReplyKeyboardMarkup:
    """Bouton natif de partage de contact.

    Telegram ne renvoie par ce bouton que le numéro de l'utilisateur lui-même,
    et il l'a déjà vérifié : c'est ce qui rend la liaison gratuite et sûre (§9).
    """
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=texts.BTN_PARTAGER_CONTACT, request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
```

- [ ] **Étape 5 : écrire le handler**

Créer `src/bot/handlers/compte.py` :

```python
"""Liaison du compte depuis Telegram (spec Phase 2 §9).

Telegram ne partage pas d'adresse email, mais son bouton natif « partager mon
contact » renvoie le numéro de l'utilisateur, DÉJÀ VÉRIFIÉ par Telegram. Comme
`users.phone` est unique et obligatoire, ce numéro suffit à retrouver le compte :
la liaison ne coûte aucun email.

Le garde-fou tient en une ligne et il est indispensable : un contact peut être
TRANSFÉRÉ. Sans `contact.user_id == message.from_user.id`, n'importe qui
transmettrait le contact d'un tiers et se grefferait sur son compte.
"""

from __future__ import annotations

from typing import Protocol

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardRemove

from src.bot import keyboards, texts
from src.core.auth import comptes
from src.core.erreurs import CompteInexistant, ContactUsurpe
from src.db.session import session_scope
from src.logging_setup import get_logger

log = get_logger(__name__)
router = Router(name="compte")


class ContactPartage(Protocol):
    """Le strict minimum de `aiogram.types.Contact` dont on a besoin."""

    phone_number: str
    user_id: int | None


def verifier_contact(contact: ContactPartage, expediteur_id: int) -> str:
    """Rend le numéro si le contact appartient bien à l'expéditeur."""
    if contact.user_id is None or contact.user_id != expediteur_id:
        raise ContactUsurpe(ContactUsurpe.code)
    return contact.phone_number


@router.message(Command("compte"))
async def cmd_compte(message: Message) -> None:
    await message.answer(
        texts.COMPTE_DEMANDER_CONTACT, reply_markup=keyboards.partager_contact()
    )


@router.message(F.contact)
async def contact_recu(message: Message) -> None:
    if message.contact is None or message.from_user is None:
        return

    try:
        numero = verifier_contact(message.contact, message.from_user.id)
    except ContactUsurpe:
        log.warning("contact_usurpe", telegram_id=message.from_user.id)
        await message.answer(
            texts.COMPTE_CONTACT_REFUSE, reply_markup=ReplyKeyboardRemove()
        )
        return

    async with session_scope() as session:
        deja = await comptes.par_telegram(session, message.from_user.id)
        if deja is not None:
            await message.answer(texts.COMPTE_DEJA_LIE, reply_markup=ReplyKeyboardRemove())
            return
        try:
            utilisateur = await comptes.lier_telegram(
                session, telephone_saisi=numero, telegram_id=message.from_user.id
            )
        except CompteInexistant:
            await message.answer(
                texts.COMPTE_INTROUVABLE, reply_markup=ReplyKeyboardRemove()
            )
            return

    log.info("compte_lie_telegram", user_id=utilisateur.id)
    await message.answer(texts.COMPTE_LIE, reply_markup=ReplyKeyboardRemove())
```

Dans `src/bot/handlers/__init__.py`, ajouter `compte` à l'import et
`root.include_router(compte.router)`.

- [ ] **Étape 6 : lancer les tests et vérifier qu'ils passent**

Lancer : `pytest tests/test_bot_compte.py tests/test_texts.py tests/test_bot_start.py -v && mypy src/`
Attendu : tous les tests PASSENT.

- [ ] **Étape 7 : commiter**

```bash
git add src/bot tests/test_bot_compte.py tests/test_texts.py
git commit -m "feat(bot): liaison de compte par contact vérifié, textes conformes au §2"
```

---

## Tâche 17 : isolation de `core` et vérification finale

**Fichiers :**
- Créer : `tests/test_core_isole.py`
- Modifier : `CLAUDE.md` (§4, arborescence — si elle a divergé), `README.md`

**Interfaces :**
- Consomme : tout ce qui précède
- Produit : la garantie que `src/core/` reste réutilisable

> C'est le test qui empêche l'architecture de se défaire en silence. Un `from fastapi import ...`
> ajouté un jour par commodité dans `core/` recouplerait la couche métier à l'API, et le bot
> traînerait FastAPI pour rien. Le test le refuse à l'écriture, pas à la relecture.

- [ ] **Étape 1 : écrire le test qui échoue**

Créer `tests/test_core_isole.py` :

```python
"""`src/core/` ne connaît aucun framework (CLAUDE.md §4).

C'est la condition qui fait de l'API et du bot deux traductions de la même
règle, et non deux copies qui divergeront.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

RACINE = Path("src/core")
INTERDITS = {"fastapi", "starlette", "aiogram", "uvicorn", "redis", "httpx"}


def _modules_importes(fichier: Path) -> set[str]:
    arbre = ast.parse(fichier.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module and noeud.level == 0:
            modules.add(noeud.module.split(".")[0])
    return modules


@pytest.mark.parametrize("fichier", sorted(RACINE.rglob("*.py")), ids=str)
def test_aucun_framework_importe(fichier: Path) -> None:
    interdits = _modules_importes(fichier) & INTERDITS
    assert not interdits, f"{fichier} importe {sorted(interdits)}"


def test_core_contient_bien_des_modules() -> None:
    """Garde-fou du garde-fou : un dossier vide rendrait le test ci-dessus creux."""
    assert len(list(RACINE.rglob("*.py"))) >= 8
```

> `redis` et `httpx` sont dans la liste **exprès** : `core` parle à Redis à travers le Protocol
> `CacheRedis`, jamais à travers le client. C'est ce qui permet aux tests unitaires de tourner
> sans réseau.

- [ ] **Étape 2 : lancer le test**

Lancer : `pytest tests/test_core_isole.py -v`
Attendu : PASSE. **S'il échoue**, c'est une vraie régression d'architecture : retirer l'import
fautif de `core/` et le remplacer par un Protocol, ne pas allonger `INTERDITS`.

- [ ] **Étape 3 : vérification complète**

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/
pytest -v
docker compose down -v && docker compose build && docker compose up -d
sleep 20 && curl -s localhost:8080/health && docker compose ps
RUN_INTEGRATION_TESTS=1 pytest -m integration -v
```

Attendu : `ruff` et `mypy` sans erreur, tous les tests au vert, `/health` en `200`, tous les
services `running` sauf `migrate` (`exited (0)`) et `web` (non démarré, profil désactivé).

- [ ] **Étape 4 : parcours manuel de bout en bout**

```bash
# 1. Demander un code
curl -s -X POST localhost:8080/auth/code/demande \
  -H 'content-type: application/json' -d '{"email":"vous@example.sn"}' -i | head -1

# 2. Lire le code dans les logs (fournisseur console)
docker compose logs api --since 1m | grep courriel_non_envoye_mode_console

# 3. S'inscrire avec ce code
curl -s -X POST localhost:8080/auth/code/verifie -c /tmp/cookies.txt \
  -H 'content-type: application/json' \
  -d '{"email":"vous@example.sn","code":"<LE CODE>","telephone":"771234567","nom_complet":"Votre Nom"}'

# 4. Vérifier la session
curl -s localhost:8080/moi -b /tmp/cookies.txt
```

Puis, dans Telegram : `/compte` → « Partager mon numéro » avec **le même numéro** →
attendre `COMPTE_LIE`. Re-vérifier `GET /moi` : `telegram_lie` doit être passé à `true`, et
`GET /moi` doit rendre **le même `id`** qu'à l'étape 3 — c'est le critère de validation n°2 de
la spec (aucun doublon entre le web et Telegram).

- [ ] **Étape 5 : mettre la documentation à jour**

Vérifier que l'arborescence du §4 de `CLAUDE.md` correspond à ce qui existe réellement (§13 :
« quand tu ajoutes un fichier au projet, mets à jour l'arborescence du §4 »). Ajouter au
`README.md` une section « Lancer l'API » avec le parcours `curl` de l'étape 4.

- [ ] **Étape 6 : commiter**

```bash
git add tests/test_core_isole.py CLAUDE.md README.md
git commit -m "test(core): interdire tout framework dans la couche métier"
```

---

## Ce qui reste après ce plan

- **Client web Next.js** — plan séparé, `docs/superpowers/plans/2026-09-11-client-web.md`.
  Écrans : adresse, code, nom et téléphone, compte avec bouton « Connecter Telegram ».
  Critère de validation : page d'inscription **sous 200 Ko transférés**.
- **Repli du lien profond** — `POST /moi/telegram/jeton` produit le lien, mais le handler
  `/start <jeton>` côté bot qui le consomme n'est pas dans ce plan. À ajouter quand le web
  affichera le bouton ; le chemin normal (« partager mon contact ») fonctionne sans lui.
- **Points ouverts de la spec §16** — nom de domaine, fournisseur d'envoi,
  `/supprimer_mes_donnees`, et les quatre questions de Phase 3 (sort du fichier CV, écran de
  validation du profil, CV scanné).
