# Phase 2 — Socle backend et comptes

> Design validé par le porteur du projet le 2026-09-11.
> Ce document est la source de vérité de la Phase 2. Le plan d'implémentation en découle.

> ⚠️ **Révisé le 2026-09-12 par `2026-09-12-retrait-telegram-design.md`.** Telegram cesse d'être un
> client du produit et le téléphone quitte la table d'identité. Ce document est **conservé tel
> quel** : il dit ce qui a été conçu le 2026-09-11, et le comprendre aide à comprendre ce qui a
> suivi. Mais il n'est plus la source de vérité sur ces points. Sont **caducs** : la ligne
> « Téléphone » du §2, le processus `bot` du §4, `phone` et `telegram_id` du §5,
> `core/telephone.py` du §6, la ligne `/moi/telegram/jeton` et le champ `telephone` du §8, le
> **§9 en entier** (liaison Telegram), `phonenumbers` du §12, les tests Telegram et téléphone du
> §13, et les critères de validation du §15 — réécrits au §8 de la spec du 2026-09-12 et repris
> dans `CLAUDE.md` §12.

---

## 1. Pourquoi ce virage, et pourquoi maintenant

Le projet était figé sur « interface = Telegram uniquement » (§2 de CLAUDE.md). Le porteur du
projet a levé cette contrainte le 2026-09-11 : il veut un **backend** servant plusieurs clients,
dont une **application web** et une **PWA mobile**.

Le moment est le bon, et ce n'est pas une opinion :

- **Les Phases 0 et 1 sont réutilisables intégralement.** `ingest/`, `normalize`, `dedupe`,
  `store`, les modèles et les migrations n'importent rien de `aiogram`. Le seul code couplé à
  Telegram est `src/bot/`, soit quatre fichiers et un handler `/start`.
- **La table `users` est vide** (vérifié le 2026-09-11 : 0 ligne, contre 232 dans `jobs`). La
  migration d'identité ne demande aucun backfill et ne touche pas les offres déjà ingérées.

Le même chantier mené après la Phase 4 — quand les documents, les quotas et le paiement seraient
écrits à l'intérieur de handlers aiogram — serait une réécriture, pas une extraction.

---

## 2. Décisions actées

| Sujet | Décision |
|---|---|
| Architecture | Couche métier réutilisable + API HTTP ; Telegram devient un client parmi d'autres |
| Premier client | Web (Next.js, TypeScript) ; le bot est remis à niveau plus tard |
| Mobile | PWA à partir du même code web ; pas d'application native |
| Authentification | **Email + code à 6 chiffres**. Pas de mot de passe, pas d'OAuth |
| Téléphone | **Obligatoire** à l'inscription (liaison Telegram + paiement §10) |
| Hébergement | Tout sur le VPS, `web` et `api` derrière le même reverse proxy |
| Dépôt | Monorepo : le client web vit dans `web/` du dépôt `jobbot` |
| Fournisseur d'envoi | Abstraction `EmailProvider` + implémentation console. Le fournisseur réel attend un domaine |

### Décisions écartées, et pourquoi

- **OTP par SMS** (envisagé puis abandonné le 2026-09-11) : chaque message se paie à l'unité, y
  compris les échecs et les renvois, ce qui ponctionne directement une marge bâtie sur 1 000 FCFA.
  L'email transactionnel est gratuit à ce volume.
- **Lien magique dans l'email** : sur Android d'entrée de gamme, un lien ouvert depuis Gmail
  atterrit fréquemment dans un navigateur différent de celui où l'inscription a commencé, et la
  session se perd. Certains antispam « pré-cliquent » aussi les liens, ce qui brûle le jeton avant
  l'utilisateur. Le code à 6 chiffres ignore ces deux problèmes.
- **Front sur Vercel, API sur le VPS** : deux origines imposent du CORS, interdisent le cookie
  `httpOnly` de première partie sans bricolage, et n'évitent pas d'avoir un domaine puisque l'API
  doit de toute façon être exposée en HTTPS.
- **Tout sur Vercel** : `worker_ingest` et `worker_match` sont des processus permanents pilotés par
  APScheduler, et le §2.4 impose 3 à 5 s entre deux requêtes de scraping. Le modèle serverless ne
  tient pas cette contrainte.
- **Table de sessions / refresh tokens** : remplacés par une colonne `users.token_version`. Voir §5.

---

## 3. Ce que ce design contredit dans CLAUDE.md

Trois contraintes gelées sont levées. Elles sont réécrites dans CLAUDE.md par le même commit que
ce document.

| § | Avant | Après |
|---|---|---|
| §2 | « Interface = Telegram uniquement », figé | Backend + clients multiples ; web d'abord |
| §7 | « Ne pas réintroduire : domaine d'envoi, SPF/DKIM/DMARC, fournisseur SMTP, bounces » | Distinction explicite : **le bot n'envoie toujours aucune candidature** (figé), mais l'**email transactionnel vers nos propres utilisateurs** est autorisé |
| §14.1 | Le nom de domaine « ne bloque plus » depuis le 2026-09-08 | Un domaine redevient nécessaire — mais pour la mise en service réelle, pas pour la Phase 2 |

**Ce qui ne bouge pas.** L'interdiction n°1 du §2 reste entière : le bot ne soumet aucune
candidature, par aucun canal. L'email transactionnel sert uniquement à vérifier l'adresse d'un
utilisateur qui s'inscrit chez nous. Il n'écrit jamais à un recruteur, ni au nom de l'utilisateur.

---

## 4. Architecture cible

### Processus

```
api            FastAPI / uvicorn — API REST JSON + /health
web            Next.js — SSR + PWA, consomme api
bot            aiogram — appelle le métier EN DIRECT, pas via HTTP
worker_ingest  inchangé
worker_match   inchangé
```

Tous sur le même VPS, tous dans `docker-compose.yml`, `web` et `api` derrière le même reverse
proxy. **Même origine** : aucun CORS à configurer, et le jeton peut vivre dans un cookie
`httpOnly` plutôt que dans `localStorage`.

### La règle métier n'existe qu'une fois

`src/core/` ne connaît ni FastAPI, ni aiogram, ni HTTP. Il expose des fonctions et des exceptions
métier. L'API les traduit en réponses HTTP, le bot les traduit en messages Telegram.

**Le bot n'appelle pas l'API par HTTP.** Il importe `src/core/` comme n'importe quel module. Pas
de saut réseau entre deux de nos propres processus, pas de jeton à gérer entre eux. On reste un
monolithe (§2.5).

### Conséquences de ménage

- `src/health.py` déménage vers `src/api/routers/sante.py`.
- `bot/main.py` perd `_run_http()` : le bot ne sert plus de HTTP.
- Le healthcheck Docker du service `bot` ne peut plus interroger un port. Il est remplacé par une
  sonde qui ne dépend pas du réseau.
- Le service `api` reprend le port `HTTP_PORT` et le healthcheck `/health` actuels.

---

## 5. Modèle de données — migration `0002`

`users` est vide : la migration est sans backfill et sans perte.

| Colonne | Avant | Après | Justification |
|---|---|---|---|
| `email` | `VARCHAR(320)` nullable | `NOT NULL UNIQUE` | Identité de connexion |
| `phone` | `VARCHAR(32)` nullable | `NOT NULL UNIQUE` | E.164 ; liaison Telegram et paiement (§10) |
| `telegram_id` | `BIGINT NOT NULL UNIQUE` | **nullable**, unicité conservée | Telegram n'est plus qu'un canal |
| `token_version` | — | `INTEGER NOT NULL DEFAULT 0` | Révocation de jetons |

### Pas de table de sessions

Un seul JWT d'accès, valable 30 jours, portant `token_version` dans ses revendications. À chaque
requête authentifiée on charge déjà l'utilisateur : on compare la valeur du jeton à celle de la
ligne. Se déconnecter de partout revient à incrémenter la colonne, et tous les jetons émis tombent
d'un coup.

Une colonne au lieu d'une table et d'un second cycle de jetons à faire tourner : c'est le §2.5
appliqué. Le prix assumé est qu'un jeton volé reste valable jusqu'à révocation explicite.

### Le code de vérification ne touche jamais Postgres

Il vit en Redis, sous forme de **HMAC-SHA256**, TTL 5 minutes, avec son compteur d'essais. Il
expire tout seul, et un dump SQL n'expose aucun code en cours de validité.

```
code:<hmac(email)>        -> hmac(code)     TTL 300 s
code:essais:<hmac(email)> -> compteur       TTL 300 s
```

---

## 6. Couche `src/core/`

| Module | Responsabilité |
|---|---|
| `core/telephone.py` | Normalisation E.164 sénégalaise. Accepte `+221 77…`, `00221 77…`, `77…` ; rejette le reste |
| `core/courriel_valide.py` | Validation syntaxique et normalisation (minuscules, espaces) de l'adresse |
| `core/erreurs.py` | Exceptions métier : `TropDeDemandes`, `CodeInvalide`, `CodeExpire`, `CompteInexistant`, `InscriptionIncomplete`, `ContactUsurpe` |

`CompteInexistant` est un signal **interne**. Il ne doit jamais être traduit en réponse par
`/auth/code/demande`, sous peine de rendre l'endpoint énumérable (§8). Un test le vérifie.
| `core/auth/codes.py` | Génération (`secrets`), hachage, vérification, compteur d'essais |
| `core/auth/jetons.py` | Encodage et décodage du JWT, contrôle de `token_version` |
| `core/auth/limites.py` | Garde-fous anti-abus, adossés à Redis |
| `core/auth/comptes.py` | Création de compte, récupération, liaison `telegram_id` |

Aucun de ces modules n'importe `fastapi` ni `aiogram`. C'est la condition qui rend la couche
réutilisable, et elle est vérifiée par un test.

---

## 7. Abstraction d'envoi — `src/courriel/`

Le package s'appelle **`courriel`** et non `email` : `email` est un module de la bibliothèque
standard Python, et le masquer est un piège d'import classique. Le nom français reste cohérent
avec `fraicheur.py` et `telephone.py`.

```python
class FournisseurCourriel(Protocol):
    async def envoyer_code(self, destinataire: str, code: str) -> None: ...
```

- `courriel/console.py` — implémentation de développement : le code part dans les logs structlog.
  C'est le **seul** endroit du projet où un code de vérification a le droit d'être journalisé.
- L'implémentation réelle (Resend, Brevo ou équivalent) est ajoutée quand un domaine existe. Elle
  n'impose aucun changement ailleurs.

Le choix du fournisseur est piloté par une variable d'environnement, avec `console` par défaut.

### Ce qui bloque l'envoi réel, et ce qui ne bloque pas

Un domaine possédé est indispensable pour poser SPF, DKIM et DMARC. Un sous-domaine `*.vercel.app`
ne convient pas : la zone DNS appartient à Vercel. Les fournisseurs de sous-domaines gratuits
partagent un domaine parent entre des milliers d'utilisateurs, largement présent sur les listes de
blocage — le code arrive en indésirables, et l'inscription échoue **sans erreur côté serveur**.

**Mais la Phase 2 est intégralement développable et testable sans domaine**, via l'implémentation
console. Pour un test avec une vraie boîte, les bacs à sable des fournisseurs acceptent d'écrire à
l'adresse vérifiée du propriétaire du compte. Le domaine ne devient indispensable qu'à l'ouverture
à de vrais utilisateurs. Il est donc consigné en point ouvert du §14, pas en blocage de phase.

---

## 8. API

| Méthode | Chemin | Rôle |
|---|---|---|
| `POST` | `/auth/code/demande` | `{email}` → `202`. Envoie un code |
| `POST` | `/auth/code/verifie` | `{email, code}` + `{telephone, nom_complet}` **si le compte n'existe pas** → jeton en cookie `httpOnly` |
| `POST` | `/auth/deconnexion` | Incrémente `token_version` |
| `GET` | `/moi` | Compte courant |
| `POST` | `/moi/telegram/jeton` | Jeton de liaison à usage unique pour le lien profond |
| `GET` | `/health` | Postgres + Redis (déplacé depuis `src/health.py`) |

### Deux règles de conception non négociables

1. **`/auth/code/demande` répond exactement pareil que l'adresse existe ou non.** Même code HTTP,
   même corps, même temps de réponse à la granularité observable. Sinon l'endpoint devient un
   annuaire qui dit publiquement qui est client.
2. **Le nom est fourni à la vérification, pas à la demande.** On ne crée une ligne `users` qu'après
   un code valide. Sinon n'importe qui remplit la table avec des adresses qu'il ne possède pas.

> **Supprimé le 2026-09-12.** Cette section portait ici une affirmation **fausse** sur
> `phone UNIQUE` : elle prétendait qu'un code valide protégeait le numéro saisi, alors qu'il ne
> prouve que la possession de l'adresse email. Elle est supprimée avec la colonne qu'elle
> décrivait, et non corrigée. Le sujet est traité par `2026-09-12-retrait-telegram-design.md`.

### Un seul endpoint pour l'inscription et la reconnexion

`/auth/code/verifie` couvre les deux cas, et c'est ce qui permet à `/auth/code/demande` de rester
indifférenciable :

- **Le compte existe** → `telephone` et `nom_complet` sont ignorés s'ils sont fournis. On connecte.
  Un utilisateur qui revient ne ressaisit jamais son numéro.
- **Le compte n'existe pas** → ces deux champs deviennent obligatoires. S'ils manquent, la réponse
  est `422` avec un code d'erreur `inscription_incomplete`, et le **code de vérification reste
  valable** pour que le client puisse afficher le formulaire complémentaire sans renvoyer d'email.

Le client web enchaîne donc : adresse → code → (formulaire nom/téléphone seulement si nouveau).
Cette réponse `422` est le seul endroit du parcours qui révèle l'existence d'un compte, et elle
n'est atteignable **qu'après** avoir prouvé la possession de l'adresse. C'est volontaire.

---

## 9. Liaison Telegram — gratuite, et sûre

Telegram ne partage pas d'adresse email, mais son bouton natif « partager mon contact » renvoie le
**numéro de l'utilisateur, déjà vérifié par Telegram**. Comme `users.phone` est unique et
obligatoire, ce numéro suffit à retrouver le compte.

**Le garde-fou qui rend ce chemin sûr** : vérifier que `contact.user_id == message.from_user.id`.
Sans lui, quelqu'un pourrait transférer le contact d'un tiers et se greffer sur son compte. Un
contact partagé qui échoue à ce test lève `ContactUsurpe`, est journalisé, et ne lie rien.

**Repli** : lien profond `t.me/<bot>?start=<jeton>`, pour qui utilise Telegram avec un numéro
différent de celui de son inscription. Le jeton est à usage unique, TTL 10 minutes, stocké en
Redis.

---

## 10. Garde-fous anti-abus

L'endpoint d'envoi est ouvert au public. Non protégé, il permet d'inonder l'adresse d'un tiers et
de brûler la réputation du futur domaine d'envoi.

| Garde-fou | Valeur par défaut | Configurable |
|---|---|---|
| Cooldown entre deux demandes pour une même adresse | 60 s | oui |
| Envois par adresse et par heure | 3 | oui |
| Envois par adresse et par jour | 10 | oui |
| Envois par IP et par heure | 10 | oui |
| Plafond global journalier | 500 | oui |
| Essais avant destruction du code | 5 | oui |

Au dépassement du plafond global : refus net et **alerte admin via `alerting.py`**, qui existe
déjà depuis la Phase 1. Jamais d'échec silencieux (§7).

**Le code de vérification n'apparaît dans aucun log structlog**, y compris en développement. La
seule exception est `courriel/console.py`, où c'est la fonction même du module.

---

## 11. Client web

Next.js + TypeScript, dans `web/`, construit en multi-étapes et servi par `next start`.

Le §11 de CLAUDE.md décrit une cible sur 3G instable avec une data comptée. Next.js est plus lourd
qu'un rendu serveur classique : la contrainte est donc tenue par la discipline, et mesurée.

- Pas de librairie de composants lourde.
- Polices locales via `next/font`, aucune requête vers un CDN de polices.
- Découpage de bundle agressif ; aucune dépendance ajoutée sans justification écrite (§3).
- **Le poids transféré de la page d'inscription est un critère de validation de phase**, pas un
  vœu : plafond fixé à 200 Ko.

Écrans de la Phase 2 : saisie de l'adresse, saisie du code, saisie du nom et du téléphone, écran
de compte avec le bouton « Connecter Telegram ». Rien d'autre.

---

## 12. Dépendances ajoutées (justification exigée par le §3)

| Paquet | Justification |
|---|---|
| `pyjwt` | Encodage et décodage du JWT. Alternative écartée : rouler sa propre signature, ce qui est une mauvaise idée en cryptographie |
| `email-validator` | Validation et normalisation d'adresse. Une regex maison sur les adresses est une source d'erreurs connue |
| `phonenumbers` | Normalisation E.164 sénégalaise. Gère les préfixes mobiles et les formats locaux mieux qu'une regex |
| `next`, `react`, `react-dom`, `typescript` | Client web, techno tranchée par le porteur du projet |

Le paquet du fournisseur d'envoi réel sera ajouté et justifié quand le domaine existera.

---

## 13. Tests

Le §13 impose un test pour tout parsing et toute règle de quota.

- `core/telephone.py` — `+221 77…`, `00221 77…`, `77…`, formats invalides, numéros étrangers.
- `core/courriel_valide.py` — adresses valides, invalides, normalisation de la casse.
- `core/auth/codes.py` — génération, vérification, expiration, code détruit après 5 essais, mauvais code.
- `core/auth/limites.py` — **chaque garde-fou du §10**, y compris le plafond global et son alerte.
- `core/auth/jetons.py` — jeton valide, expiré, altéré, et invalidé par `token_version`.
- Parcours d'inscription complet contre un fournisseur factice, **dont la non-énumération des comptes**.
- Liaison Telegram : nominal, contact usurpé (`contact.user_id != from_user.id`), numéro inconnu,
  et absence de doublon quand le compte existe déjà.
- Migration `0002` : aller-retour, via `tests/test_migrations.py` qui existe déjà.
- Un test vérifie que `src/core/` n'importe ni `fastapi` ni `aiogram`.

`mypy --strict` doit passer sur `src/`.

---

## 14. Hors périmètre de la Phase 2

Pas de mot de passe (§2.2), pas d'OAuth, pas de refresh token, pas de rôles. Pas d'upload de CV,
pas d'appel DeepSeek, pas de matching, pas de paiement. Le bot conserve `/start` et `/aide` et
gagne uniquement la liaison de compte.

**Une correction s'y greffe** parce qu'on touche au fichier : `src/bot/texts.py` promet « je
postule pour vous » dans `START` et « je peux postuler à votre place » dans `AIDE`. C'est contraire
au §2 depuis le 2026-09-08 ; seule la documentation avait été corrigée par le commit `c920cb7`.

---

## 15. Critères de validation de la phase

1. Inscription web complète : adresse → code → nom et téléphone → compte créé.
2. Depuis le bot, « partager mon contact » avec le même numéro **retombe sur le compte existant**,
   sans doublon.
3. Un contact usurpé est refusé.
4. La page d'inscription transfère **moins de 200 Ko**.
5. `docker compose up` fonctionne sur une machine vierge à partir du seul `.env.example`.
6. `mypy --strict` et la suite de tests au vert.

---

## 16. Points ouverts

1. **Nom de domaine** — nécessaire pour SPF/DKIM/DMARC et donc pour tout envoi réel. Ne bloque pas
   la Phase 2, bloque l'ouverture à de vrais utilisateurs. À trancher avant la Phase 6.
2. **Fournisseur d'envoi** — à choisir en même temps que le domaine.
3. **Politique de confidentialité et `/supprimer_mes_donnees`** (§14.4) — la Phase 2 commence à
   stocker adresse et téléphone. À trancher au plus tard en Phase 3, quand les CV arriveront.
4. **Sort du fichier CV, écran de validation du profil, CV scanné** — questions posées le
   2026-09-10, reportées en Phase 3.
5. **Agrégateur mobile money et grille de frais** (§14.2) — inchangé, toujours ouvert.
