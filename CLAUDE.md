# CLAUDE.md — Projet « JobBot Sénégal »

> Ce fichier est le brief permanent du projet. Il est lu à chaque session.
> Si une instruction de l'utilisateur contredit ce fichier, **demande confirmation avant d'agir** et propose de mettre à jour ce fichier.

---

## 1. Mission

Bot Telegram qui centralise les offres d'emploi du marché sénégalais, génère un CV adapté + une lettre de motivation via IA, et soumet la candidature à la place de l'utilisateur quand c'est possible.

Modèle économique : abonnement mensuel ~1 000 FCFA, payé en mobile money (Wave / Orange Money / Free Money).

**Utilisateur cible** : chercheur d'emploi sénégalais, 20-35 ans, smartphone Android d'entrée de gamme, connexion 3G/4G instable, data comptée. Il postule aujourd'hui manuellement sur 4-5 sites différents.

---

## 2. Contraintes non négociables

Ces points ont été tranchés par le porteur du projet. Ne les remets pas en question dans le code, mais **alerte-le** si une implémentation les rend impossibles.

| Décision | Statut |
|---|---|
| Interface = **Telegram** uniquement | Figé |
| LLM = **DeepSeek** (API compatible OpenAI) | Figé |
| Monétisation = **abonnement mensuel** (pas de packs) | Figé |
| Auto-submit = **email uniquement** au départ | Figé |
| Langue de l'interface et des documents = **français** | Figé |
| Paiement = **mobile money via agrégateur local** | Figé |

### Interdictions strictes

1. **Ne jamais automatiser la soumission sur LinkedIn, Indeed, Talent.com ou tout site à login utilisateur.** Risque de bannissement des comptes des utilisateurs. Pour ces offres : mode « brouillon » (documents générés + lien direct, l'utilisateur soumet lui-même).
2. **Ne jamais stocker de mot de passe utilisateur en clair**, et ne jamais demander le mot de passe d'une boîte mail. Si l'envoi depuis l'adresse de l'utilisateur devient nécessaire → OAuth Gmail uniquement, jamais de mot de passe applicatif saisi dans le bot.
3. **Ne jamais envoyer deux lettres de motivation structurellement identiques.** Voir §8 (anti-détection).
4. **Ne jamais scraper sans délai ni User-Agent identifiable.** Respect de `robots.txt`, 1 requête / 3-5 s par domaine.
5. **Pas de sur-ingénierie.** Pas de Kubernetes, pas de microservices, pas de Kafka. Un monolithe Python déployé sur un VPS à 5 €/mois doit tenir 5 000 utilisateurs.

---

## 3. Stack technique

```
Langage      Python 3.11+
Bot          aiogram 3.x (async)
DB           PostgreSQL 16
ORM          SQLAlchemy 2.0 (style async) + Alembic pour les migrations
Cache/Queue  Redis (rate limiting, dédoublonnage, file de jobs légère)
Scheduler    APScheduler (AsyncIOScheduler) — PAS de Celery au départ
HTTP         httpx (async)
Parsing HTML selectolax (rapide) ; BeautifulSoup seulement si le HTML est sale
LLM          DeepSeek API via le SDK openai (base_url=https://api.deepseek.com)
Docs         python-docx pour générer ; LibreOffice headless pour convertir en PDF
CV entrant   pdfplumber (PDF) + python-docx (DOCX)
Email        SMTP transactionnel (Brevo ou Resend) — voir §7
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
| `aiogram` | 0 | §3, couche bot |
| `sqlalchemy[asyncio]` + `asyncpg` | 0 | §3, ORM async ; `asyncpg` est le driver requis par SQLAlchemy async pour Postgres |
| `alembic` | 0 | §3, migrations |
| `redis` | 0 | §3, healthcheck dès la Phase 0 |
| `apscheduler` | 0 | §3, boucle des workers |
| `pydantic-settings` | 0 | §3, config |
| `structlog` | 0 | §3, logs JSON |
| `fastapi` + `uvicorn` | 0 | §4, healthcheck ; support du webhook de paiement en §10 |
| `httpx` | 0 | §3, requis par aiogram et par l'ingestion |

À ajouter plus tard : `selectolax` (Phase 1), `openai` (Phase 2), `python-docx` + `pdfplumber` (Phase 2/4).

---

## 4. Architecture

Trois processus dans le même repo, lancés séparément par Docker Compose :

```
worker_ingest   → scraping + normalisation + dédoublonnage des offres  (toutes les 2h)
worker_match    → matching offres/profils + push des alertes Telegram   (2x/jour, 8h et 18h GMT)
bot             → serveur aiogram + webhook de paiement (FastAPI monté à côté)
```

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
│   ├── health.py              # app FastAPI : /health (DB + Redis)
│   ├── worker_ingest.py       # entrypoint process worker_ingest (APScheduler)
│   ├── worker_match.py        # entrypoint process worker_match (APScheduler)
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
│   │   ├── email_apply.py     # le seul canal d'auto-submit
│   │   └── draft.py           # mode brouillon pour les sites hardened
│   ├── billing/
│   │   ├── provider.py        # abstraction agrégateur mobile money
│   │   └── webhook.py
│   ├── bot/
│   │   ├── main.py
│   │   ├── handlers/
│   │   │   └── start.py       # /start et /aide
│   │   ├── keyboards.py
│   │   └── texts.py           # TOUS les textes utilisateur ici, jamais inline
│   └── matching/
│       └── scorer.py
└── tests/
```

Les modules non encore écrits existent sous forme de package vide (`__init__.py` seul) : ils sont créés
au fil des phases, pas d'avance.

---

## 5. Modèle de données

Tables minimales (à créer via Alembic, pas de `create_all` en prod) :

**`users`** — `telegram_id` (unique, bigint), `phone`, `full_name`, `created_at`, `language`, `state` (onboarding/active/blocked)

**`profiles`** — `user_id` FK, `raw_cv_text`, `structured` (JSONB : expériences, formations, compétences, langues, secteurs visés, mobilité, prétention salariale), `cv_file_path`, `updated_at`

**`subscriptions`** — `user_id` FK, `plan` (free/pro), `status` (active/expired/pending), `started_at`, `expires_at`, `provider_ref`, `amount_fcfa`

**`jobs`** — `source`, `source_id`, `url` (unique), `title`, `company`, `location`, `contract_type`, `description`, `apply_email` (nullable), `apply_method` (email/form/external), `posted_at`, `expires_at`, `fingerprint` (pour dédoublonnage), `raw` (JSONB)

**`applications`** — `user_id` FK, `job_id` FK, `status` (draft/sent/failed/bounced), `cv_path`, `letter_path`, `sent_at`, `template_variant`, `llm_cost_usd`, `error`. **Contrainte unique `(user_id, job_id)`** — un utilisateur ne postule qu'une fois par offre.

**`usage_counters`** — `user_id`, `period` (YYYY-MM), `applications_count`, `llm_tokens_in`, `llm_tokens_out`, `cost_usd`

**`job_application_stats`** — `job_id`, `count` — sert au plafond anti-saturation (§8).

Index obligatoires : `jobs.fingerprint`, `jobs.posted_at`, `applications.user_id`, `subscriptions.expires_at`.

### Conventions retenues

- Les champs à valeurs contraintes (`state`, `plan`, `status`, `apply_method`) sont des **`VARCHAR` + `CHECK`**,
  pas des types ENUM natifs Postgres : ajouter une valeur à un ENUM natif impose une migration bloquante,
  ce qui est disproportionné ici.
- Toutes les dates sont en **UTC, `TIMESTAMPTZ`**.
- `users.email` est **nullable** : pré-rempli par le parsing du CV en Phase 2, confirmé par l'utilisateur
  avant le premier envoi (§14.5).

---

## 6. Règles métier

### Plans

| | Free | Pro (1 000 FCFA / 30 jours) |
|---|---|---|
| Alertes offres | 5/jour, sans filtre | Illimitées, filtrées par profil |
| Candidatures générées | **2 au total** (essai) | **25 / mois** |
| Envoi automatique par email | non | oui |
| Suivi + relance J+7 | non | oui |

Le quota de 25 est un **plafond de coût**, pas une limite arbitraire. Il doit être configurable par variable d'environnement (`PRO_MONTHLY_QUOTA`).

### Cycle de vie de l'abonnement

- Expiration à `expires_at`, pas de prélèvement automatique (impossible en mobile money) → **relance à J-3, J-1 et J+1**, message court avec bouton de paiement.
- 3 jours de grâce après expiration : l'utilisateur garde l'accès en lecture (alertes) mais pas la génération.
- Un paiement pendant la période active **prolonge** `expires_at`, il ne le remplace pas.

### Onboarding (doit tenir en moins de 2 minutes)

1. `/start` → présentation en 3 lignes maximum
2. Upload du CV (PDF ou DOCX) → parsing → **affichage du profil extrait pour validation** (l'utilisateur corrige en un tap)
3. Choix des secteurs + région + type de contrat (boutons inline, pas de saisie libre)
4. Première alerte envoyée immédiatement — **la valeur doit être visible avant toute demande de paiement**

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
- **Chiffre encore inconnu, à mesurer dès la première passe** : la proportion d'annonces contenant un email de candidature extractible. C'est ce qui déterminera si la source alimente vraiment l'auto-submit ou seulement le mode brouillon (§7, extraction de l'email). À remonter au porteur du projet une fois connu.

Chaque scraper hérite de `BaseScraper` et implémente `fetch_list()` et `parse_detail()`. **Chaque scraper doit avoir un test avec un fichier HTML figé dans `tests/fixtures/`** — c'est le seul moyen de détecter qu'un site a changé de structure.

Si un scraper renvoie 0 offre alors qu'il en renvoyait > 0 la veille → log niveau ERROR + notification Telegram à l'admin. Ne jamais échouer en silence.

### Extraction de l'email de candidature

C'est le cœur de la valeur. Beaucoup d'annonces sénégalaises disent simplement « envoyez CV + LM à `recrutement@xyz.sn` ».

- Regex email sur la description, puis validation : rejeter les emails du site lui-même (`@senjob.com`, etc.) et les emails génériques de webmaster.
- Si un email valide est trouvé → `apply_method = 'email'` → auto-submit possible.
- Sinon → `apply_method = 'form'` → mode brouillon obligatoire.

### Envoi de l'email

- Expéditeur : `candidatures@<domaine>` avec **nom d'affichage = nom du candidat** → `Amadou Diallo <candidatures@domaine.sn>`
- `Reply-To` = adresse email réelle du candidat. **Le recruteur doit pouvoir répondre directement au candidat, jamais au bot.**
- Objet : reprendre l'intitulé exact du poste et, si présent, la référence de l'annonce.
- Pièces jointes : `CV_Prenom_Nom.pdf` et `Lettre_Motivation_Prenom_Nom.pdf`. Jamais de .docx en pièce jointe.
- **SPF, DKIM et DMARC configurés avant le premier envoi.** Montée en charge progressive (50 mails/jour la première semaine, doublement hebdomadaire). Sans ça, tout finit en spam et le produit ne vaut rien.
- Traiter les bounces : webhook du provider → `applications.status = 'bounced'` → prévenir l'utilisateur et **ne pas décompter son quota**.

---

## 8. Anti-détection et qualité — CRITIQUE

Le marché sénégalais est petit : les mêmes recruteurs à Dakar reçoivent toutes les candidatures. Si 300 utilisateurs envoient des lettres au format identique, les recruteurs identifieront le pattern et filtreront. **Cela détruirait le produit.** Règles obligatoires :

1. **4 templates de lettre minimum**, structurellement différents (ordre des paragraphes, longueur, formule d'accroche, présence ou non de puces). Variante choisie de façon déterministe par `hash(user_id + job_id) % n` pour la reproductibilité.
2. **Aucune signature textuelle du bot** dans les documents envoyés. Pas de mention du service, pas de footer, pas de métadonnée `Author` révélatrice dans le PDF.
3. **Plafond par offre** : maximum 15 candidatures envoyées via le service pour une même offre (`job_application_stats`). Au-delà → mode brouillon uniquement, avec message honnête à l'utilisateur.
4. **Refus de postuler si le profil ne correspond pas.** Si le score de matching < seuil, le bot le dit et propose autre chose. Envoyer 25 candidatures hors-sujet nuit à l'utilisateur et brûle la réputation du domaine d'envoi.
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
- Webhook FastAPI monté sur le même process que le bot. **Vérification de signature obligatoire.** Idempotence : un même `provider_ref` traité deux fois ne crée qu'un seul abonnement.
- Toujours prévoir un **repli manuel** : commande `/paiement_manuel` qui affiche un numéro Wave et permet d'envoyer une capture d'écran à l'admin, avec activation via commande admin. Les agrégateurs tombent ; l'encaissement ne doit jamais s'arrêter.

---

## 11. Contexte terrain à respecter dans l'UX

- **Data chère et lente.** Messages courts. Pas d'images décoratives. Documents en PDF léger (< 300 Ko).
- **Beaucoup d'utilisateurs quitteront le bot pendant l'onboarding** s'il y a plus de 4 étapes. Compter et logger les abandons à chaque étape.
- Français simple, sans jargon RH. Éviter « optimiser votre employabilité » ; dire « améliorer votre CV ».
- Prévoir le tutoiement/vouvoiement cohérent (choisir le **vouvoiement**) et ne jamais mélanger.
- Toujours proposer une sortie : chaque écran a un bouton retour, `/aide` est toujours disponible.

---

## 12. Livraison par phases

Ne code pas la phase N+1 tant que la phase N n'est pas testée et validée par le porteur du projet.

**Phase 0 — Socle (1 sem.)**
Repo, Docker Compose, config, modèles + migrations, bot qui répond `/start`, healthcheck.
*Validation : `docker compose up` fonctionne sur une machine vierge à partir du seul `.env.example`.*

**Phase 1 — Ingestion (1 sem.)**
`BaseScraper`, source `emploidakar.com` (priorité n°1), ReliefWeb, puis 2 autres sites sénégalais. Normalisation, dédoublonnage, extraction d'email. Commande admin `/stats_ingest`.
*Validation : 100+ offres uniques en base, dont au moins 30 avec un email de candidature valide.*

**Phase 2 — Profil (1 sem.)**
Upload CV, parsing DeepSeek, validation par l'utilisateur, préférences.
*Validation : 10 CV réels de formats différents parsés correctement.*

**Phase 3 — Alertes (3 j.)**
Matching, push 2x/jour, filtres, désabonnement.
*Validation : un utilisateur test reçoit des offres pertinentes 2 jours de suite.*

**Phase 4 — Génération + envoi (1,5 sem.)**
CV adapté, lettre, rendu PDF, envoi email, mode brouillon, quotas.
*Validation : 5 candidatures envoyées à une adresse de test, reçues en boîte de réception (pas en spam), avec Reply-To correct.*

**Phase 5 — Paiement (1 sem.)**
Intégration agrégateur, webhook, cycle de vie de l'abonnement, relances, repli manuel.
*Validation : un paiement réel de 1 000 FCFA depuis un vrai compte Wave débloque le plan Pro en moins de 60 s.*

**Phase 6 — Exploitation (continu)**
Dashboard admin minimal (commandes Telegram suffisent), alertes sur scraper cassé, suivi coût LLM, backup Postgres quotidien.

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

1. Nom de domaine et nom du produit (nécessaire pour SPF/DKIM avant Phase 4). — **`jobbot` retenu à titre PROVISOIRE le 2026-08-26.** Domaine non choisi : bloque la Phase 4.
2. Agrégateur mobile money retenu et grille de frais réelle. — ouvert
3. Statut juridique de la structure (nécessaire pour ouvrir un compte marchand). — ouvert
4. Politique de confidentialité : les CV sont des données personnelles. Durée de conservation, suppression sur demande, commande `/supprimer_mes_donnees` à prévoir. — ouvert
5. Adresse email de l'utilisateur : collectée à l'onboarding ou déduite du CV ? (Impact direct sur le Reply-To.) — **défaut appliqué en Phase 0** : `users.email` nullable, déduit du CV en Phase 2, confirmé par l'utilisateur avant le premier envoi. À reconfirmer.

---

## 15. Notes d'exploitation

- **Le FAI du porteur de projet bloque par intermittence `api.telegram.org`** (`[Errno 101] Network is unreachable`).
  Ce n'est pas un bug du bot. En développement local, utiliser le long-polling avec un timeout court
  (`TELEGRAM_LONG_POLL_TIMEOUT=2`) et laisser aiogram se reconnecter. En production (VPS), utiliser le webhook.
