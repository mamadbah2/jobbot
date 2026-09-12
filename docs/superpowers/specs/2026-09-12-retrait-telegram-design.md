# Retrait de Telegram et du téléphone — design

**Date :** 2026-09-12
**Décidé par :** le porteur du projet, en session
**Statut :** validé, à implémenter sur la branche `worktree-phase2-socle-backend` (PR #1)

---

## 1. La décision

> « On va changer complètement d'axe. Plus de Telegram donc plus d'obligation sur quelconque
> numéro de téléphone et plus de contrôle sur le numéro de téléphone. »

Telegram cesse d'être un client du produit. Le client web devient le **seul** client, et non
plus le premier d'une série. Le numéro de téléphone quitte la table d'identité.

Le retrait est **sans retour** : le code du bot est supprimé, pas débranché. Y revenir un jour
coûterait de réécrire 512 lignes, ce qui est assumé — du code mort que `mypy`, `ruff` et
`pytest` continuent de traiter est une charge permanente, et chaque session future le croirait
vivant.

### Ce que la décision ferme gratuitement

La faille du numéro non vérifié, relevée par la revue finale de la Phase 2 et laissée ouverte
parce qu'elle appelait un arbitrage du porteur, **disparaît avec la colonne**. Il n'y a plus de
numéro à revendiquer sans preuve, donc plus de victime empêchée de s'inscrire, et plus de
rattachement Telegram détournable. La décision qui bloquait la Phase 3 n'a plus d'objet.

### Ce que la décision ouvre

Telegram portait **le seul canal d'administration prévu** : alerte de scraper cassé (§7),
commandes d'exploitation (§12 Phase 8), repli de paiement manuel (§10). Le §5 de ce document
le remplace.

---

## 2. Portée

### Supprimés en entier

| Chemin | Lignes |
|---|---|
| `src/bot/` — `main.py`, `keyboards.py`, `texts.py`, `handlers/{__init__,start,compte}.py` | 512 |
| `src/core/telephone.py` | 44 |
| `tests/test_bot_compte.py` | 457 |
| `tests/test_bot_start.py` | 70 |
| `tests/test_telephone.py` | 62 |
| Dépendances `aiogram` et `phonenumbers` de `pyproject.toml` | — |
| Service `bot` de `docker-compose.yml` | — |

### Amputés

- **`src/config.py`** — les réglages `telegram_bot_token`, `telegram_mode`,
  `telegram_long_poll_timeout`, `telegram_webhook_url`, `telegram_webhook_secret`,
  `telegram_bot_username` et `admin_telegram_id` partent. `admin_courriel: str = ""` arrive.
  Le type `TelegramMode` disparaît.
- **`src/core/erreurs.py`** — `NumeroInvalide`, `TelephoneDejaUtilise`, `ContactUsurpe`,
  `TelegramDejaLie` et `LiaisonIndisponible` sont supprimées, avec leurs traductions HTTP dans
  `src/api/app.py`.
- **`src/core/auth/comptes.py`** — `par_telephone`, `par_telegram`, `lier_telegram` et
  `definir_telephone` sont supprimées. `connecter_ou_inscrire` perd son paramètre de téléphone.
- **`src/api/routers/moi.py`** — l'endpoint `/moi/telegram/jeton` est supprimé, avec sa
  mécanique de jeton à usage unique en Redis (clés `jobbot:auth:liaison*`, dérivation de clé
  `"liaison"`, TTL de 600 s).
- **`src/api/schemas/auth.py`** — la réponse `Utilisateur` perd `telephone` et `telegram_lie`.
- **`src/db/models.py`** — `User` perd `phone` et `telegram_id`.
- **`src/core/auth/cles.py`** — le `Usage = Literal["jeton", "code", "limite", "liaison"]`
  perd `"liaison"`, et sa docstring la mention des jetons de liaison Telegram. La dérivation
  d'une clé par usage, elle, reste entière : c'est une propriété de sécurité indépendante de
  Telegram.
- **`src/logging_setup.py`** — le paragraphe de commentaire expliquant pourquoi `aiogram.event`
  n'était **pas** filtré. Il n'y a aucun filtre à retirer : seul `uvicorn.error` en porte un,
  et il reste.
- **`.env.example`**, **`README.md`**, **`CLAUDE.md`** (§7 de ce document).

### Intacts, et c'est le point

`src/ingest/` (les 232 offres et leurs scrapers), `src/core/auth/{codes,jetons,limites}.py`,
`src/core/{cache,courriel_valide,saisie}.py`, `src/courriel/`, `src/api/routers/sante.py`,
`src/db/session.py`.

La **signature** du protocole `AlerteAdmin` (`src/core/alerte.py`) ne change pas d'une ligne :
c'était exactement sa raison d'être. Seule sa docstring, qui citait Telegram en exemple de canal
possible, est retouchée.

`src/api/routers/auth.py` ne garde que deux commentaires à réécrire : ils expliquent pourquoi
`NumeroInvalide` et `TelephoneDejaUtilise` ne peuvent plus remonter de cet endpoint, et
renvoient vers `comptes.definir_telephone` qui disparaît. Son code, lui, est inchangé.

---

## 3. Modèle de données

`users` après la migration : `id`, `email` (NOT NULL, UNIQUE, indexée), `full_name`,
`token_version`, `created_at`, `language`, `state`. Rien d'autre.

### Migration `0005_retrait_telephone_telegram`

`down_revision = "a1c2e3f40004"`, `revision = "a1c2e3f40005"`.

- `upgrade()` : `DROP COLUMN phone`, `DROP COLUMN telegram_id`. Postgres supprime avec elles
  leurs index uniques, il n'y a rien d'autre à défaire.
- `downgrade()` : recrée les deux colonnes en `NULL` avec leurs index uniques. **Les données ne
  sont pas restaurées** — la rétrogradation rend le schéma, pas le contenu. Acceptable ici : la
  base de développement porte 0 utilisateur, et aucune base de production n'existe.

**La migration `0004` est conservée** alors qu'elle ne fait que rendre `phone` facultatif, ce
que `0005` achève en le supprimant. Une histoire idéale n'aurait qu'une migration ; rétrograder
`0004` pour la réécrire imposerait un `alembic downgrade` sur la base de développement qui
porte les 232 offres, pour un gain purement cosmétique. Deux migrations, zéro risque.

---

## 4. Surface de l'API

Cinq endpoints, un de moins qu'aujourd'hui :

| Endpoint | Corps | Inchangé ? |
|---|---|---|
| `POST /auth/code/demande` | `{email}` | oui |
| `POST /auth/code/verifie` | `{email, code, nom_complet?}` | oui — le téléphone en était déjà sorti (commit `f2ca5ac`) |
| `POST /auth/deconnexion` | — | oui |
| `GET /moi` | — | la réponse perd `telephone` et `telegram_lie` |
| `GET /health` | — | oui |

L'étape 1 de l'onboarding (§6 du CLAUDE.md) devient : **adresse email → code à 6 chiffres →
nom**. Deux champs au lieu de trois, ce qui sert la contrainte du §11 (au-delà de quatre étapes,
les utilisateurs abandonnent).

---

## 5. Canal d'administration

### Alertes vers le porteur : `AlerteCourriel`

Une seconde implémentation du protocole `AlerteAdmin` existant, dans `src/alerting.py`, à côté
de `AlerteJournalisee`. Elle délègue l'envoi au `FournisseurCourriel` déjà écrit pour les codes
de connexion.

Conséquences voulues :

- en développement, le fournisseur `console` écrit l'alerte dans les logs — soit exactement le
  comportement actuel, aucune régression de confort ;
- en production, le fournisseur réel l'envoie à `ADMIN_COURRIEL` ;
- **aucun appelant n'est modifié** : `src/core/auth/limites.py` et le worker d'ingestion ne
  connaissent que le protocole.

`construire_alerte()` choisit `AlerteCourriel` si `ADMIN_COURRIEL` est renseigné, et
`AlerteJournalisee` sinon. Une alerte qui n'a personne à prévenir doit rester traçable dans les
logs du VPS, et le dire dans son événement plutôt que de se croire transmise.

**Le bac à sable d'un fournisseur transactionnel sait envoyer vers l'adresse vérifiée du
propriétaire du compte sans domaine possédé.** Les alertes admin sont donc exploitables avant
que le §14.1 soit tranché, contrairement aux emails vers de vrais utilisateurs.

### Actions d'administration : CLI sur le VPS

`/stats_ingest`, l'activation manuelle d'un abonnement et l'état des scrapers deviennent des
commandes lancées sur le VPS (`docker compose exec api python -m …`). **Aucune n'est écrite
dans ce virage** : aucune n'a de besoin réel avant la Phase 6. Le §14 du CLAUDE.md les consigne
comme tranchées-non-faites, et non comme question ouverte.

Un espace admin dans l'application web a été écarté : c'est une fonctionnalité à construire et
à sécuriser (rôle, autorisations), pas un effet de bord de ce retrait.

---

## 6. Configuration

`.env.example` perd ses sept variables `TELEGRAM_*` / `ADMIN_TELEGRAM_ID` et gagne
`ADMIN_COURRIEL=`.

**`TELEGRAM_BOT_TOKEN` était la seule valeur obligatoire du fichier**, et elle l'était pour
*tous* les processus — l'API et les workers refusaient de démarrer sans elle. Après ce retrait,
`.env.example` se copie en `.env` et la pile démarre **sans qu'aucune valeur soit renseignée**.
Le critère de validation de la Phase 0 (« fonctionne sur une machine vierge à partir du seul
`.env.example` ») devient vrai sans réserve.

`docker-compose.yml` passe de cinq à quatre services : `api`, `web`, `worker_ingest`,
`worker_match` (plus `postgres`, `redis`, `migrate`).

---

## 7. Réécriture du CLAUDE.md

Sections à modifier, avec ce qui change :

| § | Modification |
|---|---|
| §1 Mission | Le produit est accessible par une application web (PWA). La phrase sur le bot comme client de plein droit disparaît. |
| §2 Contraintes | La ligne « Premier client = web ; Telegram remis à niveau ensuite » devient « Client unique = web (Next.js, PWA) », figée le 2026-09-12. La ligne d'authentification perd toute mention de téléphone. |
| §3 Stack | Les lignes `Bot aiogram 3.x` et `phonenumbers` partent du tableau et de l'inventaire des dépendances de la Phase 2. |
| §4 Architecture | Quatre processus. Le paragraphe « le bot n'appelle pas l'API par HTTP » n'a plus d'objet mais **la règle qu'il servait reste** : `src/core/` est la seule copie de la règle métier, et son test d'isolation demeure. L'arborescence perd `src/bot/`, `src/core/telephone.py` et `/moi/telegram/jeton`. |
| §5 Modèle | `users` perd `phone` et `telegram_id`. L'encadré expliquant pourquoi `phone` était devenu facultatif est remplacé par une note courte disant qu'il a été supprimé, et pourquoi. |
| §6 Règles métier | L'onboarding étape 1 devient « email → code → nom ». Tout le paragraphe sur « partager mon contact » et le garde-fou `contact.user_id == message.from_user.id` disparaît. |
| §7 Sources et envoi | L'alerte de scraper cassé va à l'admin **par email**, plus par Telegram. La livraison du dossier (Phase 5) se fait par téléchargement depuis le web, plus par message Telegram. |
| §10 Paiement | Le repli manuel `/paiement_manuel` devient une page web ; l'activation se fait par commande CLI. |
| §11 UX | `/aide` côté Telegram disparaît ; seul son équivalent web subsiste. Le comptage des abandons d'onboarding ne concerne plus que le web. |
| §12 Phases | **La Phase 7 (« Bot Telegram remis au niveau du web ») est supprimée.** Les critères de validation de la Phase 2 sont réécrits (§8 ci-dessous). La Phase 8 remplace « commandes Telegram suffisent » par les commandes CLI. |
| §14 Points ouverts | Ajout du canal d'administration comme tranché-non-fait. Le point 7 ne mentionne plus le téléphone parmi les données stockées. |
| §15 Notes d'exploitation | La note sur le FAI qui bloque `api.telegram.org` est supprimée : sans bot, elle n'a plus d'objet. |

Le document de spec `2026-09-11-socle-backend-design.md` porte à son §8 une affirmation
**fausse** (« on ne crée une ligne `users` qu'après un code valide, sinon `phone UNIQUE`
devient un moyen de bloquer le numéro d'autrui ») : elle est supprimée avec la colonne qu'elle
décrivait, et non corrigée.

---

## 8. Critères de validation de la Phase 2, réécrits

Les critères actuels testent « partager mon contact » et le refus d'un contact usurpé : ils
n'ont plus d'objet. Ils deviennent :

1. Inscription web complète de bout en bout : adresse → code lu dans les logs → nom → session.
2. Une seconde connexion avec la même adresse retombe sur le **même** compte, sans doublon.
3. La déconnexion invalide le jeton : le rejouer renvoie 401.
4. Page d'inscription **sous 200 Ko transférés**.

Les critères 1 à 3 sont vérifiables dès ce retrait, par `curl` contre l'API. Le critère 4
appartient au client web, qui n'existe pas encore (§10 ci-dessous).

---

## 9. Tests

### Supprimés

`tests/test_bot_compte.py`, `tests/test_bot_start.py`, `tests/test_telephone.py`.

### À adapter

`tests/conftest.py` — il injecte `TELEGRAM_BOT_TOKEN` dans l'environnement de **toute** la
suite (aujourd'hui obligatoire pour construire `Settings`) ; cette ligne part, et avec elle les
quatre autres occurrences réparties dans `test_config.py` et `test_worker_ingest.py`.

Puis : `test_api_auth_verifie.py`, `test_api_moi.py`, `test_auth_comptes.py`,
`test_config.py`, `test_core_isole.py`, `test_identite_migration.py`, `test_migrations.py`,
`test_logs_sans_pii.py`, `test_alerting.py`, `test_sante_scraper.py`, `test_worker_ingest.py`.

`test_core_isole.py` **reste** et garde sa valeur : il vérifie que `src/core/` n'importe ni
`fastapi` ni `aiogram`. La partie `aiogram` devient triviale, la partie `fastapi` est la vraie
protection et la règle du §4 est inchangée.

### À ajouter

- **`AlerteCourriel`** : l'alerte part bien par le fournisseur ; `construire_alerte()` choisit
  `AlerteJournalisee` quand `ADMIN_COURRIEL` est vide ; une panne du fournisseur ne fait pas
  échouer l'appelant — une alerte qui explose en essayant de signaler un incident aggrave
  l'incident.
- **Migration `0005`** : après `upgrade`, les colonnes `phone` et `telegram_id` sont absentes
  de `users` ; `downgrade` les recrée nullables.
- **Garde anti-retour** : aucun fichier de `src/` n'importe `aiogram`, et `aiogram` n'est pas
  dans les dépendances déclarées. Sans ce test, Telegram peut revenir par un import isolé sans
  que rien ne le signale.

---

## 10. Hors périmètre

- **Le client web Next.js.** C'est le vrai reste-à-faire de la Phase 2 : le plan du backend
  annonçait à sa ligne 22 ne couvrir que le backend, et le plan séparé
  `docs/superpowers/plans/2026-09-11-client-web.md` n'a jamais été écrit. Il fait l'objet de sa
  propre séance de conception, après ce retrait.
- Les commandes CLI d'administration (§5) — Phase 6.
- L'écart connu de la table `applications` (contrainte `CHECK` héritée du modèle avec envoi
  automatique) — Phase 4, comme déjà prévu.
- Le nom de domaine et le fournisseur d'email transactionnel (§14.1, §14.6) — inchangés, et
  toujours bloquants pour la Phase 6 seulement.

---

## 11. Arbitrages assumés

| Choix | Coût s'il s'avère faux |
|---|---|
| Supprimer le bot au lieu de le débrancher | Réécrire 512 lignes si Telegram redevient un client. Le bot était simple ; le coût est borné. |
| Conserver `0004` et ajouter `0005` | Deux migrations pour un seul mouvement du schéma. Lisible, et sans `downgrade` sur la base qui porte les 232 offres. |
| Supprimer `users.phone` plutôt que le garder facultatif | Si un besoin de numéro apparaît, il faudra une migration. Mais le numéro existera de toute façon dans `profiles.structured` en Phase 3, extrait du CV : la colonne aurait fait doublon, avec la question « lequel fait foi ». |
| Alertes admin par email plutôt qu'espace web | Une alerte qui n'arrive pas si l'envoi d'email tombe. Les logs du VPS restent le repli, et `AlerteJournalisee` ne disparaît pas. |
| Retravailler la branche plutôt que fusionner puis nettoyer | La PR #1 grossit. Mais `main` ne reçoit jamais de code qu'on sait faux, et le porteur ne relit qu'une fois — il n'avait laissé aucun commentaire de revue, rien n'est invalidé. |
