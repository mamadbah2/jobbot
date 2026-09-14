# CLAUDE.md — Projet « JobBot Sénégal »

> Ce fichier est le brief permanent du projet. Il est lu à chaque session.
> Si une instruction de l'utilisateur contredit ce fichier, **demande confirmation avant d'agir** et propose de mettre à jour ce fichier.

---

## 1. Mission

Service qui centralise les offres d'emploi du marché sénégalais, repère celles qui correspondent au profil de l'utilisateur, et prépare pour chacune un CV adapté + une lettre de motivation via IA. **C'est l'utilisateur qui dépose sa candidature**, jamais le service.

Accessible par **une application web (et PWA mobile)**, au-dessus d'un backend qui porte toute la règle métier. Un bot Telegram fut l'unique interface jusqu'au 2026-09-11, puis un client parmi d'autres ; il a été **retiré le 2026-09-12**, et le web est désormais le **seul** client.

Modèle économique : abonnement mensuel ~1 000 FCFA, payé en mobile money (Wave / Orange Money / Free Money).

**Utilisateur cible** : chercheur d'emploi sénégalais, 20-35 ans, smartphone Android d'entrée de gamme, connexion 3G/4G instable, data comptée. Il postule aujourd'hui manuellement sur 4-5 sites différents.

---

## 2. Contraintes non négociables

Ces points ont été tranchés par le porteur du projet. Ne les remets pas en question dans le code, mais **alerte-le** si une implémentation les rend impossibles.

| Décision | Statut |
|---|---|
| Architecture = **couche métier + API**, plusieurs clients | Figé le 2026-09-11 |
| Client unique = **web (Next.js, PWA)** | Figé le 2026-09-12 — révise « premier client = web ; Telegram remis à niveau ensuite » (2026-09-11). Le retrait de Telegram est **sans retour** : le code du bot est supprimé, pas débranché |
| Mobile = **PWA** issue du même code web, pas d'application native | Figé le 2026-09-11 |
| Authentification = **email + code à 6 chiffres**, l'adresse est la seule identité de connexion — **aucun numéro de téléphone** | Figé le 2026-09-12 — le téléphone était obligatoire (2026-09-11), puis facultatif (2026-09-12) ; la colonne est supprimée, cf. §5 |
| Hébergement = **tout sur le VPS**, `web` et `api` sur la même origine | Figé le 2026-09-11 |
| LLM = **DeepSeek** (API compatible OpenAI) | Figé |
| Monétisation = **abonnement mensuel** (pas de packs) | Figé |
| **Aucun envoi de candidature par le service** — il prépare, l'utilisateur dépose | Figé le 2026-09-08 (dit « par le bot » à l'époque, le bot étant alors le seul client) |
| Langue de l'interface et des documents = **français** | Figé |
| Paiement = **mobile money via agrégateur local** | Figé |

### Interdictions strictes

1. **Ne jamais soumettre une candidature à la place de l'utilisateur, par aucun canal.** Ni formulaire, ni site à login, ni email. Le service produit les documents et indique où déposer ; le dépôt est toujours un geste de l'utilisateur. Cette règle était limitée aux sites à login (LinkedIn, Indeed, Talent.com) ; elle a été **généralisée le 2026-09-08** par le porteur du projet. Conséquence : il n'y a plus de « mode brouillon » à distinguer, c'est le seul mode.
2. **Aucun mot de passe utilisateur, nulle part.** L'authentification se fait par email + code à usage unique : il n'y a donc pas de mot de passe à stocker, à hacher, ni à réinitialiser. Ne jamais demander le mot de passe d'une boîte mail. Si l'envoi depuis l'adresse de l'utilisateur devenait nécessaire → OAuth Gmail uniquement.
   **Corollaire depuis le 2026-09-11** : le code de vérification ne vit qu'en Redis, haché, avec un TTL de 5 minutes. Il n'entre jamais en base, et n'apparaît dans aucun log — sauf dans le fournisseur d'envoi « console » de développement, où c'est sa raison d'être.
3. **Ne jamais envoyer deux lettres de motivation structurellement identiques.** Voir §8 (anti-détection).
4. **Ne jamais scraper sans délai ni User-Agent identifiable.** Respect de `robots.txt`, 1 requête / 3-5 s par domaine.
5. **Pas de sur-ingénierie.** Pas de Kubernetes, pas de microservices, pas de Kafka. Un monolithe Python déployé sur un VPS à 5 €/mois doit tenir 5 000 utilisateurs.

---

## 3. Stack technique

```
Langage      Python 3.11+
API          FastAPI (le cœur : tous les clients passent par là)
Web          Next.js + React + TypeScript, servi en PWA
Auth         JWT via pyjwt — email + code à 6 chiffres, aucun mot de passe
DB           PostgreSQL 16
ORM          SQLAlchemy 2.0 (style async) + Alembic pour les migrations
Cache/Queue  Redis (rate limiting, dédoublonnage, file de jobs légère)
Scheduler    APScheduler (AsyncIOScheduler) — PAS de Celery au départ
HTTP         httpx (async)
Parsing HTML selectolax (rapide) ; BeautifulSoup seulement si le HTML est sale
LLM          DeepSeek API via le SDK openai (base_url=https://api.deepseek.com)
Docs         python-docx pour générer ; LibreOffice headless pour convertir en PDF
CV entrant   pdfplumber (PDF) + python-docx (DOCX)
Config       pydantic-settings, tout par variables d'environnement
Logs         structlog en JSON
Tests        pytest + pytest-asyncio
Déploiement  Docker Compose sur VPS (Hetzner CX22 ou équivalent)
```

**Aucune dépendance supplémentaire sans justification écrite dans le PR.**

### Dépendances installées à ce jour (Phase 0)

Les paquets sont ajoutés phase par phase, pas tous d'un coup, pour garder l'image Docker légère.

| Paquet | Phase | Justification |
|---|---|---|
| `sqlalchemy[asyncio]` + `asyncpg` | 0 | §3, ORM async ; `asyncpg` est le driver requis par SQLAlchemy async pour Postgres |
| `alembic` | 0 | §3, migrations |
| `redis` | 0 | §3, healthcheck dès la Phase 0 |
| `apscheduler` | 0 | §3, boucle des workers |
| `pydantic-settings` | 0 | §3, config |
| `structlog` | 0 | §3, logs JSON |
| `fastapi` + `uvicorn` | 0 | §4, healthcheck ; support du webhook de paiement en §10 |
| `httpx` | 0 | §3, client HTTP async de l'ingestion (et des tests d'API) |

### Dépendances ajoutées en Phase 2

| Paquet | Justification |
|---|---|
| `pyjwt` | §4, jetons d'accès. Rouler sa propre signature est une mauvaise idée en cryptographie |
| `email-validator` | §5, validation et normalisation d'adresse ; une regex maison est une source d'erreurs connue |
| `next`, `react`, `react-dom`, `typescript` | §3, client web |

> **Retirées le 2026-09-12** : `aiogram` (Phase 0, couche bot) et `phonenumbers` (Phase 2,
> normalisation E.164) partent avec Telegram et le téléphone. Un test garde-fou vérifie
> qu'`aiogram` ne revient ni dans `src/` ni dans les dépendances déclarées : sans lui, Telegram
> pourrait rentrer par un import isolé sans que rien ne le signale.

À ajouter plus tard : `openai` (Phase 3), `python-docx` + `pdfplumber` (Phase 3/5), le paquet du
fournisseur d'envoi d'email (quand un domaine existera, cf. §14.1).

---

## 4. Architecture

Quatre processus dans le même repo, lancés séparément par Docker Compose (le service `bot` a été
supprimé le 2026-09-12) :

```
api             → FastAPI : API REST JSON + /health + webhook de paiement (§10)
web             → Next.js : interface web et PWA, consomme api
worker_ingest   → scraping + normalisation + dédoublonnage des offres  (toutes les 2h)
worker_match    → matching offres/profils + push des alertes            (2x/jour, 8h et 18h GMT)
```

**`web` et `api` sont servis sur la même origine**, derrière le même reverse proxy : aucun CORS à
configurer, et le jeton vit dans un cookie `httpOnly` plutôt que dans `localStorage`.

**La règle métier n'existe qu'une fois, dans `src/core/`.** Ce package n'importe ni `fastapi` ni
`aiogram` — un test le vérifie, et il le vérifie encore après le retrait de Telegram : c'est la
garantie qu'un second client, s'il en revenait un, ne trouverait aucune règle à réécrire. L'API
traduit `src/core/` en HTTP ; c'est aujourd'hui son unique traducteur.

**Aucun de nos processus n'appelle l'API par HTTP** : ceux qui ont besoin de la règle métier
importent `src/core/` en direct. Pas de saut réseau entre deux de nos propres processus. On reste
un monolithe (§2.5).

Arborescence cible :

```
jobbot/
├── CLAUDE.md
├── README.md
├── .gitignore
├── pyproject.toml
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── src/
│   ├── config.py              # pydantic Settings
│   ├── logging_setup.py       # structlog JSON, appelé par chaque entrypoint
│   ├── alerting.py            # alerte admin par email ou par log (scraper cassé, source bloquée)
│   ├── worker_ingest.py       # entrypoint process worker_ingest (APScheduler)
│   ├── worker_match.py        # entrypoint process worker_match (APScheduler)
│   ├── core/                  # MÉTIER PUR — n'importe ni fastapi ni aiogram
│   │   ├── courriel_valide.py # validation + normalisation d'adresse
│   │   ├── erreurs.py         # exceptions métier, traduites par chaque client
│   │   ├── saisie.py          # contrôles communs à toute saisie utilisateur (bornes, type)
│   │   ├── alerte.py          # Protocol AlerteAdmin — `core` ignore COMMENT l'alerte part
│   │   ├── cache.py           # Protocol CacheRedis — le minimum dont `core` a besoin,
│   │   │                      #   sans dépendre du client `redis` (test d'isolation, tâche 17)
│   │   └── auth/
│   │       ├── cles.py        # dérive une clé par usage depuis JWT_SECRET (limite/code/jeton)
│   │       ├── codes.py       # génération, hachage, vérification du code à 6 chiffres
│   │       ├── jetons.py      # encodage/décodage JWT + contrôle de token_version
│   │       ├── limites.py     # garde-fous anti-abus (Redis)
│   │       └── comptes.py     # connexion ou inscription à partir de la seule adresse email
│   ├── courriel/              # nommé `courriel` et NON `email` : `email` est stdlib
│   │   ├── provider.py        # interface FournisseurCourriel
│   │   └── console.py         # impl. de dev : le code part dans les logs
│   ├── api/
│   │   ├── main.py            # entrypoint du process `api` (uvicorn + setup_logging)
│   │   ├── app.py             # construction de l'app FastAPI
│   │   ├── deps.py            # session DB, utilisateur courant
│   │   ├── schemas/           # entrées/sorties pydantic
│   │   │   ├── auth.py
│   │   │   └── offres.py      # projection explicite d'une offre, pas un dump du modèle
│   │   └── routers/
│   │       ├── auth.py        # /auth/code/demande, /auth/code/verifie, /auth/deconnexion
│   │       ├── moi.py         # /moi
│   │       ├── offres.py      # /offres, liste paginée réservée aux comptes connectés
│   │       └── sante.py       # /health (DB + Redis) — déplacé depuis src/health.py
│   ├── db/
│   │   ├── models.py
│   │   └── session.py
│   ├── ingest/
│   │   ├── base.py            # classe abstraite BaseScraper
│   │   ├── sources/           # un fichier par source
│   │   │   ├── emploidakar.py  # source prioritaire n°1 (via admin-ajax.php)
│   │   │   ├── senjob.py
│   │   │   ├── emploisenegal.py
│   │   │   ├── recrutement_sn.py
│   │   │   ├── offre_emploi_sn.py
│   │   │   ├── novojob.py
│   │   │   └── reliefweb.py   # API officielle, sans risque de casse
│   │   ├── normalize.py       # nettoyage + extraction email de contact
│   │   ├── fraicheur.py       # rafraîchissement à la demande + verrou Redis
│   │   ├── pagination.py      # politique de pagination incrémentale
│   │   ├── robots.py          # lecture de robots.txt (robotparser inutilisable, cf §7)
│   │   ├── store.py           # écriture des offres (upsert sur source+source_id)
│   │   └── dedupe.py
│   ├── llm/
│   │   ├── client.py          # wrapper DeepSeek + retry + compteur de coût
│   │   ├── prompts.py         # tous les prompts système, versionnés
│   │   ├── cv_parser.py       # CV brut -> profil structuré
│   │   ├── cv_tailor.py       # profil + offre -> CV adapté
│   │   └── cover_letter.py
│   ├── docs/
│   │   ├── render.py          # profil -> .docx -> .pdf
│   │   └── templates/         # 4 templates .docx distincts minimum
│   ├── apply/
│   │   └── draft.py           # dossier prêt à déposer + où déposer (seul mode)
│   ├── billing/
│   │   ├── provider.py        # abstraction agrégateur mobile money
│   │   └── webhook.py
│   └── matching/
│       └── scorer.py
├── tests/
└── web/                       # client Next.js (TypeScript), même dépôt
    ├── app/
    │   ├── layout.tsx          # <html lang="fr">, police système (§11)
    │   ├── page.tsx            # racine : redirige vers /connexion ou /offres
    │   ├── not-found.tsx       # 404 en français, avec une sortie (§11) — Server Component
    │   ├── ecran-panne.tsx     # écran de panne partagé par les pages qui appellent l'API
    │   ├── icon.svg            # favicon ; évite un GET /favicon.ico en 404 à chaque page
    │   ├── styles.css
    │   ├── textes.ts           # TOUS les textes utilisateur ici, jamais inline dans les composants
    │   ├── journal.ts          # journal des abandons de parcours (§11), étapes typées
    │   ├── api-contrat.ts      # contrat d'API partagé : erreurs, cookies, leurs attributs
    │   ├── api-client.ts       # couche réseau vers `api` (server-only, jamais côté navigateur)
    │   ├── sante/
    │   │   └── route.ts        # sonde du healthcheck compose ; jamais un écran instrumenté
    │   ├── connexion/
    │   │   ├── page.tsx        # saisie de l'adresse
    │   │   ├── actions.ts      # Server Action : demande de code
    │   │   ├── expiree/
    │   │   │   └── route.ts    # efface le cookie périmé puis renvoie (interdit dans une page)
    │   │   └── code/
    │   │       ├── page.tsx    # saisie du code (+ nom si compte nouveau)
    │   │       └── actions.ts  # Server Action : vérification du code, création du compte
    │   ├── compte/
    │   │   ├── page.tsx        # adresse, nom, état, déconnexion
    │   │   └── actions.ts      # Server Action : déconnexion (incrémente token_version)
    │   └── offres/
    │       └── page.tsx        # liste des offres, déclenche rafraichir_si_necessaire
    ├── public/
    │   └── .gitkeep             # dossier vide requis par le Dockerfile (COPY --from=build)
    ├── test/
    │   ├── api-contrat.test.ts
    │   └── api-client.test.ts  # transport du cookie, absence de X-Forwarded-For sans proxy
    ├── Dockerfile              # build multi-étapes, serveur `standalone` en production
    ├── .dockerignore           # exclut node_modules/.next/.env* du contexte de build
    ├── mesure-poids.mjs        # mesure le poids transféré, sans dépendance (§11)
    ├── next.config.ts          # output: "standalone", images non optimisées
    ├── package.json
    ├── package-lock.json       # requis par `npm ci` dans l'étage `deps` du Dockerfile
    └── tsconfig.json
```

Les modules non encore écrits existent sous forme de package vide (`__init__.py` seul) : ils sont créés
au fil des phases, pas d'avance.

---

## 5. Modèle de données

Tables minimales (à créer via Alembic, pas de `create_all` en prod) :

**`users`** — `id`, `email` (unique, **NOT NULL** — identité de connexion), `token_version` (int, révocation des jetons), `full_name`, `created_at`, `language`, `state` (onboarding/active/blocked). **Rien d'autre.**

> **`phone` et `telegram_id` ont été supprimées le 2026-09-12** (migration `0005`). `phone` était
> `UNIQUE` alors qu'un code reçu par email ne prouve jamais la possession d'un numéro saisi au
> clavier : n'importe qui pouvait donc réserver le numéro d'autrui et bloquer son inscription.
> Le porteur du projet a tranché en retirant la colonne plutôt qu'en la rendant facultative
> (migrations `0004` puis `0005`). Le numéro de l'utilisateur réapparaîtra en Phase 3 dans
> `profiles.structured`, extrait du CV : une colonne d'identité aurait fait doublon, avec la
> question « lequel fait foi ». `telegram_id` part avec le client Telegram.

> **Pas de table de sessions.** Un seul JWT d'accès de 30 jours, portant `token_version`. On charge
> déjà l'utilisateur à chaque requête authentifiée : on compare la valeur du jeton à celle de la
> ligne. Se déconnecter de partout = incrémenter la colonne. Une colonne plutôt qu'une table et un
> second cycle de jetons (§2.5). Prix assumé : un jeton volé reste valable jusqu'à révocation.

> **Le code de vérification ne touche jamais Postgres.** Il vit en Redis, haché en HMAC-SHA256,
> TTL 5 minutes. Pas de compteur d'essais sur le code lui-même : c'est le plafond de cadence
> par adresse (`auth_verifications_par_heure`, `src/config.py`) qui protège contre la force brute.

**`profiles`** — `user_id` FK, `raw_cv_text`, `structured` (JSONB : expériences, formations, compétences, langues, secteurs visés, mobilité, prétention salariale), `cv_file_path`, `updated_at`

**`subscriptions`** — `user_id` FK, `plan` (free/pro), `status` (active/expired/pending), `started_at`, `expires_at`, `provider_ref`, `amount_fcfa`

**`jobs`** — `source`, `source_id`, `url` (unique), `title`, `company`, `location`, `contract_type`, `description`, `apply_email` (nullable), `apply_method` (email/form/external), `posted_at`, `expires_at`, `fingerprint` (pour dédoublonnage), `raw` (JSONB)

**`applications`** — `user_id` FK, `job_id` FK, `status` (draft/ready/deposed/failed — le service n'envoie rien, `deposed` est déclaré par l'utilisateur), `cv_path`, `letter_path`, `sent_at`, `template_variant`, `llm_cost_usd`, `error`. **Contrainte unique `(user_id, job_id)`** — un utilisateur ne postule qu'une fois par offre.

> ⚠️ **Écart connu entre ce document et la base.** La table `applications` créée en
> Phase 0 porte encore la contrainte `CHECK` d'origine (`draft/sent/failed/bounced`)
> et une colonne `sent_at`, héritées du modèle avec envoi automatique. Migration à
> faire **en Phase 4**, quand cette table sera réellement écrite pour la première
> fois — pas avant : rien ne l'utilise aujourd'hui et une migration à vide n'a
> aucun intérêt.

**`usage_counters`** — `user_id`, `period` (YYYY-MM), `applications_count`, `llm_tokens_in`, `llm_tokens_out`, `cost_usd`

**`job_application_stats`** — `job_id`, `count` — sert au plafond anti-saturation (§8).

Index obligatoires : `jobs.fingerprint`, `jobs.posted_at`, `applications.user_id`, `subscriptions.expires_at`.

### Conventions retenues

- Les champs à valeurs contraintes (`state`, `plan`, `status`, `apply_method`) sont des **`VARCHAR` + `CHECK`**,
  pas des types ENUM natifs Postgres : ajouter une valeur à un ENUM natif impose une migration bloquante,
  ce qui est disproportionné ici.
- Toutes les dates sont en **UTC, `TIMESTAMPTZ`**.
- `users.email` est **`NOT NULL UNIQUE`** : c'est l'identité de connexion depuis le 2026-09-11
  (§14.5). Cette ligne affirmait l'inverse — « nullable, pré-rempli par le parsing du CV » —
  jusqu'au 2026-09-12 : reliquat du modèle où l'adresse était déduite du CV, contredit par la
  définition de `users` ci-dessus depuis un jour.

---

## 6. Règles métier

### Plans

| | Free | Pro (1 000 FCFA / 30 jours) |
|---|---|---|
| Alertes offres | 5/jour, sans filtre | Illimitées, filtrées par profil |
| Candidatures générées | **2 au total** (essai) | **25 / mois** |
| Dossier complet prêt à déposer (CV adapté + lettre) | non | oui |
| Suivi + relance J+7 | non | oui |

Le quota de 25 est un **plafond de coût**, pas une limite arbitraire. Il doit être configurable par variable d'environnement (`PRO_MONTHLY_QUOTA`).

### Cycle de vie de l'abonnement

- Expiration à `expires_at`, pas de prélèvement automatique (impossible en mobile money) → **relance à J-3, J-1 et J+1**, message court avec bouton de paiement.
- 3 jours de grâce après expiration : l'utilisateur garde l'accès en lecture (alertes) mais pas la génération.
- Un paiement pendant la période active **prolonge** `expires_at`, il ne le remplace pas.

### Onboarding (doit tenir en moins de 2 minutes)

1. Adresse email → code à 6 chiffres → nom (le nom uniquement si le compte est nouveau)
2. Upload du CV (PDF ou DOCX) → parsing → **affichage du profil extrait pour validation** (l'utilisateur corrige en un tap)
3. Choix des secteurs + région + type de contrat (boutons, pas de saisie libre)
4. Première alerte envoyée immédiatement — **la valeur doit être visible avant toute demande de paiement**

> **Par quel canal ?** Les alertes offres partaient par Telegram jusqu'au 2026-09-12 ; leur canal
> de remplacement est **tranché depuis le 2026-09-14** (§14.9) : notifications push web d'abord,
> email périodique ensuite. Le push étant refusable et peu fiable sur Android d'entrée de gamme,
> la **première** alerte de l'étape 4 doit être visible à l'écran, pas seulement poussée.

Le parcours n'existe que sur le web. L'étape 1 demande **deux champs au lieu de trois** depuis le
2026-09-12 : c'est autant de repris sur la contrainte du §11, où chaque étape supplémentaire coûte
des abandons.

> **Supprimé le 2026-09-12 avec le client Telegram** : le parcours « partager mon contact », qui
> retrouvait ou complétait un compte à partir du numéro vérifié par Telegram, et son garde-fou
> `contact.user_id == message.from_user.id`. Plus de numéro dans `users`, donc plus rien à
> rattacher par ce chemin (§5).

---

## 7. Sources d'offres et envoi

### Priorité d'implémentation des sources

1. **`emploidakar.com`** — **priorité n°1, tranchée par le porteur du projet le 2026-09-01.** Considérée comme la meilleure source du marché local. WordPress + WP Job Manager. Voir ci-dessous les contraintes techniques relevées : elles ne sont pas optionnelles.
2. **ReliefWeb** — API publique, documentée, gratuite, stable. Offres ONG/international basées à Dakar, bien rémunérées, peu exploitées par la concurrence. **Seule source sans risque de casse** : c'est elle qui valide `BaseScraper`, `normalize` et `dedupe` sans dépendre de la santé d'un site tiers.
3. `senjob.com`, `emploisenegal.com`, `recrutement.sn`, `offre-emploi.sn`, `novojob.com` — scraping HTML.
4. Expat-Dakar (section emploi) — volume élevé, qualité variable.

### emploidakar.com — reconnaissance du 2026-09-01

Constats de terrain, à respecter dans `sources/emploidakar.py` :

- **Point d'entrée = `admin-ajax.php`, pas le HTML de liste.** Les offres ne sont pas dans le HTML de `/offres-demploi-au-senegal/` : WP Job Manager les charge en AJAX via `POST /wp-admin/admin-ajax.php` avec `action=job_manager_get_listings`. Le `robots.txt` du site **autorise explicitement** `/wp-admin/admin-ajax.php` (`Allow:` au milieu d'un `Disallow: /wp-admin/`). C'est donc le chemin propre et documenté.
- **L'API REST WordPress est un piège.** `/wp-json/wp/v2/job-listings` est bien déclarée (`rest_base = job-listings`), mais Cloudflare renvoie un challenge « Just a moment… » (HTTP 403) dès la 2e ou 3e requête, y compris sur `/wp-json/wp/v2/posts`. **Ne pas construire le scraper dessus.**
- **Interdiction de franchir le challenge Cloudflare.** Pas de User-Agent de navigateur usurpé, pas de solveur de challenge, pas de navigateur headless pour passer l'interstitiel. C'est de l'évasion de détection, exclue par §2.4, et un bannissement d'IP au niveau Cloudflare emporterait **tous** les scrapers hébergés sur le même VPS. Si l'endpoint AJAX venait à passer lui aussi sous challenge : on arrête cette source et on remonte le problème au porteur du projet, on ne contourne pas.
- **Rythme validé** : User-Agent identifiable + 5 à 8 s entre requêtes → les pages publiques répondent en 200 de façon stable, y compris après que le challenge se soit déclenché sur `/wp-json/`. Ne pas descendre sous le plancher de §2.4.
- **Zones interdites par `robots.txt`, à coder en liste noire explicite** : `/resume/`, `/CV/`, `/wp-content/uploads/job_applications/` (CVthèque et candidatures déposées par des tiers). Aucune utilité pour nous, et ce sont des données personnelles appartenant à autrui.
- **Mesuré le 2026-09-08, première passe réelle** : 232 offres ingérées, **40 % avec un email de candidature** (93), 46 % renvoyant vers un site externe (106), 14 % vers le formulaire du portail (33). Aucune entrée écartée, aucune sur-capture d'adresse. Cela ne conditionne plus un envoi (§2), mais la qualité de l'aide au dépôt : 40 % des offres se déposent par un simple email, les 46 % « external » demandent un compte sur un ATS tiers.

Chaque scraper hérite de `BaseScraper` et implémente `fetch_list()` et `parse_detail()`. **Chaque scraper doit avoir un test avec un fichier HTML figé dans `tests/fixtures/`** — c'est le seul moyen de détecter qu'un site a changé de structure.

Si un scraper renvoie 0 offre alors qu'il en renvoyait > 0 la veille → log niveau ERROR + **alerte email à l'admin** (`ADMIN_COURRIEL`, `src/alerting.py`). Le canal était Telegram jusqu'au 2026-09-12. Sans destinataire configuré, l'alerte retombe sur le log du VPS **et le dit dans son événement**, pour qu'on ne la croie pas transmise. Ne jamais échouer en silence.

> **Vigilance depuis le 2026-09-12 : une alerte admin sort maintenant du VPS.** Tant que le canal
> était le log, son rayon d'exposition était un fichier sur notre machine. `AlerteCourriel` recopie
> **tout le contexte reçu** dans le corps du message, qui part par le réseau chez un fournisseur
> transactionnel. Les appels existants ont été relus le 2026-09-12 : ils ne transportent que des
> noms de source, des compteurs, le domaine d'une adresse (jamais l'adresse entière) et
> `erreur=str(exc)` — aucun code de vérification, aucun jeton, aucune adresse d'utilisateur.
> **`erreur=str(exc)` est le champ à surveiller** : c'est la seule chaîne **libre** des contextes,
> donc le seul qui puisse emporter n'importe quoi le jour où l'exception change. **Règle pour la
> suite : tout nouvel appel à `.envoyer()` doit justifier ce qu'il met dans son contexte**, et
> regarder d'abord ses champs libres. Un code de vérification qui y passerait
> violerait l'interdiction n°2 du §2, qui interdit qu'il sorte de Redis autrement que vers son
> destinataire — et le violerait sans qu'aucun test de log ne le voie.

### Extraction de l'email de candidature

C'est le cœur de la valeur. Beaucoup d'annonces sénégalaises disent simplement « envoyez CV + LM à `recrutement@xyz.sn` ».

- Regex email sur la description, puis validation : rejeter les emails du site lui-même (`@senjob.com`, etc.) et les emails génériques de webmaster.
- `apply_method` (`email` / `form` / `external`) ne sert plus à décider d'un envoi : il sert à **dire à l'utilisateur comment déposer**. C'est le « facilite d'y déposer » de la mission (§1).
- Email trouvé → on l'affiche, avec un objet de message prêt à copier.
- Sinon → on donne le lien direct (`apply_url`) vers le formulaire ou le site externe.

### Livraison du dossier à l'utilisateur

Le service n'envoie rien à un recruteur. Il remet à l'utilisateur, **en téléchargement depuis le web**, de quoi déposer en moins d'une minute.

- Deux fichiers : `CV_Prenom_Nom.pdf` et `Lettre_Motivation_Prenom_Nom.pdf`. **Jamais de .docx** — l'utilisateur doit pouvoir les transférer tels quels.
- Le mode de dépôt, tiré de `apply_method` : adresse email à qui écrire, ou lien direct vers le formulaire.
- Un objet de message prêt à copier : intitulé exact du poste + référence de l'annonce si elle existe.
- Un rappel court : que le recruteur répondra à **son** adresse à lui, puisque c'est lui qui envoie.

**Révision du 2026-09-11 — deux choses à ne plus confondre.**

- **Le service n'envoie aucune candidature, par aucun canal. Toujours figé.** Il n'écrit jamais à un
  recruteur, ni en son nom propre ni au nom de l'utilisateur. L'interdiction n°1 du §2 est entière.
- **L'email transactionnel vers nos propres utilisateurs est autorisé**, et uniquement pour vérifier
  l'adresse de quelqu'un qui s'inscrit chez nous. S'y ajoute depuis le 2026-09-12 l'alerte
  d'exploitation vers `ADMIN_COURRIEL`, c'est-à-dire vers nous-mêmes.

Ce second point réintroduit donc, à petite échelle : un domaine d'envoi, SPF/DKIM/DMARC, un
fournisseur transactionnel. C'est le prix de l'authentification par email, tranchée le 2026-09-11.
La gestion des bounces reste volontairement hors périmètre : une adresse mal saisie se manifeste
par un code qui n'arrive pas, et l'utilisateur ressaisit.

**Un sous-domaine gratuit ne convient pas.** SPF, DKIM et DMARC se posent dans la zone DNS du
domaine ; sur `*.vercel.app` elle appartient à Vercel. Les fournisseurs de sous-domaines gratuits
partagent un domaine parent entre des milliers d'utilisateurs, largement présent sur les listes de
blocage : le code arrive en indésirables et l'inscription échoue **sans erreur côté serveur** —
le pire mode de défaillance possible. Cf. §14.1.

---

## 8. Anti-détection et qualité — CRITIQUE

Le marché sénégalais est petit : les mêmes recruteurs à Dakar reçoivent toutes les candidatures. Si 300 utilisateurs envoient des lettres au format identique, les recruteurs identifieront le pattern et filtreront. **Cela détruirait le produit.** Règles obligatoires :

1. **4 templates de lettre minimum**, structurellement différents (ordre des paragraphes, longueur, formule d'accroche, présence ou non de puces). Variante choisie de façon déterministe par `hash(user_id + job_id) % n` pour la reproductibilité.
2. **Aucune signature textuelle du service** dans les documents remis. Pas de mention du service, pas de footer, pas de métadonnée `Author` révélatrice dans le PDF.
3. **Plafond par offre** : maximum 15 candidatures préparées via le service pour une même offre (`job_application_stats`). Comportement au-delà du plafond : **non tranché, §14.10** — l'ancienne règle (« mode brouillon uniquement ») décrivait un monde où « brouillon » se distinguait d'un envoi ; depuis le §2, interdiction n°1, c'est le seul mode, donc elle ne prescrit plus rien d'applicable.
4. **Refus de postuler si le profil ne correspond pas.** Si le score de matching < seuil, le service le dit et propose autre chose. Envoyer 25 candidatures hors-sujet nuit à l'utilisateur et à la crédibilité du service auprès des recruteurs — pas à la réputation d'un domaine d'envoi que nous n'utilisons jamais pour écrire à un recruteur (§2, §7).
5. **Jamais d'invention.** Le LLM ne doit produire aucune expérience, diplôme, certification ou durée qui ne figure pas dans le profil. Cette règle est répétée dans chaque prompt système et vérifiée par un post-contrôle : toute entreprise ou tout diplôme cité dans la lettre doit exister dans `profiles.structured`, sinon régénération.

---

## 9. Couche LLM (DeepSeek)

- Client unique dans `llm/client.py`, jamais d'appel direct ailleurs.
- Utiliser `deepseek-chat`. Vérifier les tarifs et noms de modèles en cours sur la doc officielle avant de figer quoi que ce soit — ne te fie pas à une valeur en dur.
- **Activer le context caching** : le profil utilisateur est identique d'une candidature à l'autre → le placer en tête du prompt pour bénéficier du cache et réduire fortement le coût en entrée.
- `temperature` basse (0.3) pour le parsing de CV, moyenne (0.8) pour la lettre.
- **Sortie structurée en JSON** pour le parsing de CV et le matching. Parsing défensif : nettoyer les fences ``` avant `json.loads`, et retry une fois en cas d'échec.
- Retry avec backoff exponentiel sur 429 et 5xx, timeout à 60 s, **fallback explicite** : si DeepSeek est indisponible, message clair à l'utilisateur et quota non décompté. Jamais de plantage silencieux.
- **Logger le coût de chaque appel** dans `usage_counters`. Objectif : coût LLM par candidature < 15 FCFA. Si le coût moyen dépasse ce seuil, alerter l'admin — la marge de l'abonnement en dépend directement.
- Tous les prompts dans `llm/prompts.py`, avec un numéro de version en constante. Aucun prompt inline dans le code métier.

---

## 10. Paiement mobile money

- Interface abstraite `billing/provider.py` avec `create_payment(user, amount) -> checkout_url` et `verify(payload) -> PaymentResult`. **Une seule implémentation concrète au départ**, mais l'abstraction est obligatoire : les agrégateurs locaux changent de conditions.
- Comparer PayDunya, InTouch et Naboo sur : frais fixes par transaction, fiabilité du webhook, délai de settlement. **Attention au frais plancher** : sur un ticket de 1 000 FCFA, un minimum à 100 FCFA représente 10 % du revenu — remonter ce chiffre au porteur du projet dès qu'il est connu.
- Webhook FastAPI servi par le process `api`. Il l'était par le process `bot` jusqu'au 2026-09-11 ; ce process n'existe plus depuis le 2026-09-12. **Vérification de signature obligatoire.** Idempotence : un même `provider_ref` traité deux fois ne crée qu'un seul abonnement.
- Toujours prévoir un **repli manuel**. L'exigence est métier et ne bouge pas : les agrégateurs tombent, et l'encaissement ne doit jamais s'arrêter. Son canal, lui, est à redéfinir : la commande Telegram `/paiement_manuel` a disparu le 2026-09-12 avec le bot. Forme pressentie, **non tranchée** (§14.8) : une page web qui affiche un numéro Wave et accepte une capture d'écran, et une activation par commande CLI sur le VPS. À décider au plus tard en Phase 6.

---

## 11. Contexte terrain à respecter dans l'UX

- **Data chère et lente.** Messages courts. Pas d'images décoratives. Documents en PDF léger (< 300 Ko).
- **Beaucoup d'utilisateurs abandonneront pendant l'onboarding** s'il y a plus de 4 étapes. Compter et logger les abandons à chaque étape du parcours web.
- **Le web ne dispense pas de la sobriété.** Next.js est plus lourd qu'un rendu serveur classique : pas de librairie de composants lourde, découpage de bundle agressif. Le poids transféré est un **critère de validation de phase**, pas un vœu.
- Police **système** (`system-ui`), pas de fichier de police téléchargé : zéro octet
  transféré et aucun saut de mise en page au chargement. Révise le 2026-09-13 la consigne
  « polices locales via next/font », qui coûtait 15 à 40 Ko sur un budget de 200 Ko.
- Français simple, sans jargon RH. Éviter « optimiser votre employabilité » ; dire « améliorer votre CV ».
- Prévoir le tutoiement/vouvoiement cohérent (choisir le **vouvoiement**) et ne jamais mélanger.
- Toujours proposer une sortie : chaque écran a un bouton retour, et une aide est joignable depuis n'importe quel écran.

---

## 12. Livraison par phases

Ne code pas la phase N+1 tant que la phase N n'est pas testée et validée par le porteur du projet.

**Phase 0 — Socle (1 sem.)**
Repo, Docker Compose, config, modèles + migrations, healthcheck. (La Phase 0 livrait aussi un bot Telegram répondant `/start` ; il a été supprimé le 2026-09-12.)
*Validation : `docker compose up` fonctionne sur une machine vierge à partir du seul `.env.example`.*

**Phase 1 — Ingestion (1 sem.)**
`BaseScraper`, source `emploidakar.com` (priorité n°1), ReliefWeb, puis 2 autres sites sénégalais. Normalisation, dédoublonnage, extraction d'email. Statistiques d'ingestion pour l'admin (prévues en commande Telegram `/stats_ingest` ; deviennent une commande CLI sur le VPS, §14.8 — **non écrites à ce jour**).
*Validation : 100+ offres uniques en base, dont au moins 30 avec un email de candidature valide.*

> **Plan révisé le 2026-09-11** (bascule vers un backend multi-clients). Les Phases 0 et 1 sont
> conservées telles quelles : rien dans l'ingestion ne connaissait Telegram, tout est réutilisable.

**Phase 2 — Socle backend et comptes (1 sem.)**
Extraction de `src/core/`, API FastAPI, authentification email + code à 6 chiffres, migration
d'identité, abstraction d'envoi d'email, écrans web d'inscription.
Design détaillé : `docs/superpowers/specs/2026-09-11-socle-backend-design.md`, **révisé par**
`docs/superpowers/specs/2026-09-12-retrait-telegram-design.md` (retrait de Telegram et du téléphone).
*Validation, réécrite le 2026-09-12 :*
1. *Inscription web complète de bout en bout : adresse → code lu dans les logs → nom → session.*
2. *Une seconde connexion avec la même adresse retombe sur le **même** compte, sans doublon.*
3. *La déconnexion invalide le jeton : le rejouer renvoie 401.*
4. *Page d'inscription **sous 200 Ko transférés**.*

> Les critères 1 à 3 se vérifient par `curl` contre l'API (parcours du `README.md`). Le critère 4
> appartient au client web, qui reste à écrire : c'est le vrai reste-à-faire de la Phase 2.

> Les quatre critères passent depuis le 2026-09-13. Le client web existe, le critère 4 est
> mesuré par `web/mesure-poids.mjs` et doublé en vrai navigateur.

**Phase 3 — Profil (1 sem.)**
Upload CV, parsing DeepSeek, validation par l'utilisateur, préférences. Exposé par l'API, consommé
par le web.
*Validation : 10 CV réels de formats différents parsés correctement.*

**Phase 4 — Offres et alertes (3 j.)**
Matching, filtres, alertes 2x/jour par **notifications push web** (§14.9, tranché le 2026-09-14).
La liste des offres en lecture seule existe déjà, livrée avec le client web.
Le push impose la **PWA** — service worker et clés VAPID — qui cesse donc d'être optionnelle.
L'estimation de 3 jours date d'avant ce choix et ne couvrait pas le service worker.
*Validation : un utilisateur test reçoit des offres pertinentes 2 jours de suite, **et** le cas
d'un utilisateur qui refuse les notifications reste utilisable — il doit pouvoir consulter ses
offres sans jamais rien recevoir.*

**Phase 5 — Génération des documents (1 sem.)**
CV adapté, lettre, rendu PDF, remise du dossier avec le mode de dépôt, quotas.
*Validation : 5 dossiers générés pour 5 offres réelles, PDF < 300 Ko, ouverts sans erreur sur un Android d'entrée de gamme, et chacun indiquant correctement où déposer.*

**Phase 6 — Paiement (1 sem.)**
Intégration agrégateur, webhook, cycle de vie de l'abonnement, relances, repli manuel.
**Un nom de domaine est indispensable au plus tard ici** (§14.1) : sans lui, aucun email réel ne part.
*Validation : un paiement réel de 1 000 FCFA depuis un vrai compte Wave débloque le plan Pro en moins de 60 s.*

> **La Phase 7 (« Bot Telegram remis au niveau du web ») a été supprimée le 2026-09-12.** La
> numérotation des phases suivantes est **conservée telle quelle** : elle est citée ailleurs dans
> le dépôt (`src/alerting.py` renvoie à « CLAUDE.md §7, §12 Phase 8 »). Un trou dans la
> numérotation coûte moins qu'une renumérotation qui périmerait des commentaires de code.

**Phase 8 — Exploitation (continu)**
Administration par **commandes CLI sur le VPS** (`docker compose exec api python -m …`) : statistiques d'ingestion, état des scrapers, activation manuelle d'un abonnement. Alertes sur scraper cassé par email (§7), suivi coût LLM, backup Postgres quotidien. Aucun espace admin web : ce serait une fonctionnalité à construire et à sécuriser (rôle, autorisations), pas un effet de bord du retrait de Telegram.

---

## 13. Règles de travail pour Claude Code

- **Avant de coder une phase, propose un plan court et attends la validation.** Ne pars pas sur 2 000 lignes d'un coup.
- Commits atomiques, messages en français, format `feat(ingest): scraper senjob`.
- **Tout scraper, toute fonction de parsing et toute règle de quota doit avoir un test.** Le reste : tests si le code est non trivial.
- Type hints partout. `mypy` doit passer sans erreur sur `src/`.
- Aucun secret en dur. Aucun `print()` — `structlog` uniquement.
- Si une décision technique a un impact business (coût, marge, risque légal, délivrabilité), **arrête-toi et pose la question** plutôt que de choisir seul.
- Si tu constates qu'une contrainte du §2 rend une fonctionnalité impossible ou dangereuse, dis-le explicitement au lieu de contourner.
- Quand tu ajoutes un fichier au projet, mets à jour l'arborescence du §4 de ce fichier.

---

## 14. Points ouverts à trancher avec le porteur du projet

À poser dès la Phase 0, les réponses conditionnent le code :

1. Nom de domaine et nom du produit. — **`jobbot` retenu à titre PROVISOIRE le 2026-08-26.** **Redevenu nécessaire le 2026-09-11** avec l'authentification par email : SPF, DKIM et DMARC exigent un domaine possédé, et un sous-domaine gratuit ne convient pas (§7). **Ne bloque pas la Phase 2** — elle se développe et se teste intégralement avec le fournisseur d'envoi « console », et un bac à sable de fournisseur permet même de recevoir de vrais emails sur l'adresse vérifiée du propriétaire du compte. **Bloque l'ouverture à de vrais utilisateurs, donc la Phase 6.** Ordre de grandeur : 7 000 à 8 500 FCFA par an pour un `.com`. — ouvert
2. Agrégateur mobile money retenu et grille de frais réelle. — ouvert
3. Statut juridique de la structure (nécessaire pour ouvrir un compte marchand). — ouvert
4. Politique de confidentialité : les CV sont des données personnelles. Durée de conservation, suppression sur demande, action « supprimer mes données » à prévoir dans le web. Elle n'a jamais été écrite : elle était prévue en commande Telegram `/supprimer_mes_donnees`, et se reporte sur le web depuis le 2026-09-12. — ouvert
5. Adresse email de l'utilisateur. — **Rouvert et tranché le 2026-09-11** : l'adresse devient l'**identité de connexion**, `users.email` passe `NOT NULL UNIQUE`. Elle ne sert toujours pas de Reply-To, puisque le service n'écrit à aucun recruteur (§2, interdiction n°1).

6. Fournisseur d'envoi d'email transactionnel. — à choisir en même temps que le domaine. — ouvert

7. Politique de confidentialité et suppression des données sur demande (voir point 4). — La Phase 2 stocke l'adresse email et le nom ; la Phase 3 y ajoutera les CV. À trancher **au plus tard en Phase 3**.

8. **Canal d'administration.** — **Posé le 2026-09-12.** Telegram portait le seul canal admin prévu : alerte de scraper cassé (§7), repli de paiement manuel (§10), exploitation courante (§12 Phase 8). Une seule des trois est réglée.
   - *Tranché et fait* : les alertes partent par email vers `ADMIN_COURRIEL`, avec repli sur le log du VPS quand il est vide.
   - *Tranché, non fait* : les actions d'exploitation (statistiques d'ingestion, état des scrapers, activation manuelle d'un abonnement) deviennent des commandes CLI sur le VPS. Aucune n'est écrite ; aucune n'a de besoin réel avant la Phase 6.
   - *Non tranché* : **par où passe le repli de paiement manuel côté utilisateur** (§10) ? Une page web qui affiche un numéro Wave et reçoit une capture d'écran est la piste, mais elle demande un écran, un stockage de pièce jointe et une modération — ce n'est pas un effet de bord du retrait de Telegram. À décider avec le porteur du projet avant la Phase 6.

9. **Par quel canal les alertes offres arrivent-elles à l'utilisateur ?** — **Posé le 2026-09-12, TRANCHÉ le 2026-09-14 : notifications push web d'abord, email périodique plus tard.** Ne bloque plus la Phase 4.
   Le brief promet des alertes **poussées et récurrentes** : `worker_match` « push des alertes » (§4), 5/jour en Free et illimitées en Pro (§6), « première alerte envoyée immédiatement » à l'étape 4 de l'onboarding (§6), 2x/jour en Phase 4 (§12), validées par « un utilisateur test reçoit des offres pertinentes 2 jours de suite ».
   **Ce canal était Telegram, et il n'a pas été remplacé.** Le seul client est une PWA, et le §7 n'autorise l'email transactionnel que pour la vérification d'adresse et l'alerte admin. L'exigence métier survit — la valeur doit être visible avant toute demande de paiement (§6) — mais **aucun canal ne la porte aujourd'hui**.
   **Décision du porteur du projet, le 2026-09-14 : les notifications push web d'abord ; l'email périodique viendra ensuite, quand le domaine existera.**

   Ce que ce choix achète : le push ne dépend d'aucun nom de domaine, ne consomme presque pas de data (quelques centaines d'octets par message, ce qui compte sur une data comptée), et **la Phase 4 reste autonome** au lieu de se retrouver bloquée par le §14.1.

   Ce qu'il coûte, et qu'il faut assumer les yeux ouverts : le push est **refusable d'un tap**, et les gestionnaires de batterie agressifs des Android d'entrée de gamme tuent les services en arrière-plan. **Une partie des utilisateurs ne recevra donc jamais d'alerte, sans qu'on puisse le savoir.** Conséquence directe sur l'onboarding (§6) : « la première alerte envoyée immédiatement » ne peut pas reposer sur le push seul — elle doit être **visible à l'écran** au moment où l'utilisateur finit son inscription, le push ne servant qu'aux alertes suivantes.

   Conséquences techniques : le push exige HTTPS, un service worker et des clés VAPID. **La PWA, reportée en Phase 4 lors de la conception du client web, n'est donc plus optionnelle** : c'est le même service worker qui porte les deux. Mesurer son poids comme le reste (§11).

   **L'email périodique reste la cible à terme**, pour rattraper ceux que le push n'atteint pas. Il est reporté, pas abandonné, et son arrivée impose alors : nom de domaine possédé avec SPF/DKIM/DMARC (§14.1), fournisseur d'envoi (§14.6), **désabonnement obligatoire**, et la gestion des rebonds que le §7 avait mise hors périmètre. C'est un tout autre régime que le code de vérification : à rouvrir explicitement le jour où on s'y met, pas à traiter comme une extension naturelle.

10. **Que se passe-t-il au-delà du plafond de 15 candidatures préparées pour une même offre ?** — **Posé le 2026-09-13, non tranché.**
    Le §8.3 fixe le plafond, mais sa conséquence — « mode brouillon uniquement » — décrivait le monde d'avant le 2026-09-08 : un mode où l'utilisateur pouvait recevoir un dossier sans dépôt possible par le service, distinct d'un mode où le service déposait à sa place. Depuis que l'interdiction n°1 du §2 s'est généralisée, **il n'y a plus qu'un seul mode** : le service prépare toujours, l'utilisateur dépose toujours. La règle du §8.3 prescrit donc, au-delà de 15, l'état déjà universel en-dessous : elle ne change plus rien.
    Options, sans préférence de ma part : refuser de préparer un nouveau dossier pour cette offre une fois le plafond atteint (le compteur devient un vrai garde-fou) ; continuer à préparer mais avertir l'utilisateur que l'offre est saturée et le laisser décider ; ou ne rien faire et garder `job_application_stats` comme pure statistique, sans effet sur le comportement. C'est un choix produit — il détermine si la table sert à quelque chose — et il appartient au porteur du projet. **Ne pas coder la Phase 5 avant qu'il soit tranché** — c'est elle qui écrit réellement `job_application_stats` pour la première fois.

---

## 15. Notes d'exploitation

- **Aucune note en cours.** La seule qui figurait ici — le FAI du porteur de projet bloquant par
  intermittence `api.telegram.org` — a été retirée le 2026-09-12 : sans bot, elle n'a plus d'objet.
