# Client web — design

**Date :** 2026-09-13
**Décidé par :** le porteur du projet, en séance de conception
**Statut :** validé, à implémenter
**Ferme :** la Phase 2, dont c'est le seul reste-à-faire

---

## 1. Pourquoi ce document

Le backend de la Phase 2 est fini, testé et fusionné (PR #1, `54fd4e4`). Trois des quatre
critères de validation de la phase passent. **Le quatrième ne peut pas passer** : « page
d'inscription sous 200 Ko transférés » suppose une page d'inscription, et il n'existe pas un
fichier sous `web/`.

Le §11 de `2026-09-11-socle-backend-design.md` listait les écrans prévus. Il est **périmé** : il
décrit la saisie d'un téléphone et un bouton « Connecter Telegram », tous deux supprimés le
2026-09-12. Ce document le remplace.

Le plan `docs/superpowers/plans/2026-09-11-client-web.md`, cité à plusieurs endroits du dépôt,
**n'a jamais été écrit**. Ne pas le chercher.

---

## 2. Décisions prises en séance

| Question | Décision | Raison |
|---|---|---|
| Périmètre | Écrans d'authentification **+ liste des offres en lecture seule** | La base porte 232 offres réelles ; une application vide ne se valide pas |
| JavaScript navigateur | **Zéro composant client** | Les écrans doivent fonctionner quand le runtime Next n'arrive jamais — cas réel sur 3G qui coupe |
| Accès aux offres | **Réservée aux comptes connectés** | Une liste publique intégrale redistribue gratuitement le fruit du scraping et vide l'intérêt d'un compte |
| PWA | **Reportée en Phase 4** | Rien à mettre en cache hors ligne en Phase 2 ; un formulaire d'inscription a besoin du réseau |
| Couture Next ↔ API | **Server Actions** | Le cookie est posé par `cookies().set()` au lieu d'être transcrit à la main — c'est là que l'alternative se trompe en silence |
| Police | **Police système**, pas `next/font` | Zéro octet transféré, aucun saut de mise en page. **Révise le §11 du CLAUDE.md** |
| Port de l'API | **Rabattu sur `127.0.0.1`** | Sinon on contourne Next et on se forge l'IP de son choix |

---

## 3. Contraintes héritées, non négociables

- **Plafond de 200 Ko transférés** sur la page d'inscription. Critère de validation de phase
  (CLAUDE.md §11 et §12), pas un vœu.
- **Vouvoiement**, français simple, aucun jargon RH.
- **Aucun texte utilisateur en clair dans un composant.** Convention héritée de
  `src/bot/texts.py`, qui survit au bot.
- **Aucune dépendance sans justification écrite** (CLAUDE.md §3).
- **Aucune donnée personnelle dans les journaux.** Le dépôt porte deux tests dont c'est l'objet
  (`tests/test_logs_sans_pii.py`, `tests/test_logs_sans_pii_uvicorn_reel.py`).
- **La base de développement est partagée et porte 232 offres réelles.** Jamais de
  `docker compose down -v`, jamais d'`alembic downgrade`.

---

## 4. Ce que l'API offre déjà

```
POST /auth/code/demande     {email}                      → 202, corps vide
POST /auth/code/verifie     {email, code, nom_complet?}  → 200 {id,email,nom_complet,etat} + Set-Cookie
POST /auth/deconnexion      (cookie)                     → 204
GET  /moi                   (cookie)                     → 200 {id,email,nom_complet,etat}
GET  /health                                             → 200
```

Deux propriétés à ne pas casser :

1. **`/auth/code/demande` ne consulte jamais la base**, exprès. Il répond pareil que l'adresse
   existe ou non. Sans cela il devient un annuaire public de la clientèle.
2. **L'API ne renvoie jamais de phrase.** Sur erreur : `{"erreur": "<code>"}`, plus un en-tête
   `Retry-After` sur `trop_de_demandes`. Les phrases appartiennent au client.

Les neuf codes, relevés dans `src/core/erreurs.py` :

| Code | HTTP | Où il apparaît |
|---|---|---|
| `adresse_invalide` | 422 | Saisie de l'adresse |
| `trop_de_demandes` | 429 | Les deux écrans — porte `Retry-After` |
| `plafond_global_atteint` | 503 | Saisie de l'adresse |
| `envoi_impossible` | 503 | Saisie de l'adresse |
| `code_invalide` | 400 | Saisie du code |
| `code_expire` | 400 | Saisie du code |
| `inscription_incomplete` | 422 | Saisie du code — **pilote un écran, pas une erreur** (§5) |
| `nom_invalide` | 422 | Saisie du nom |
| `jeton_invalide` | 401 | `/offres`, `/compte` |

---

## 5. Écrans et parcours

Quatre routes. Le §11 du brief dit que l'onboarding perd ses utilisateurs au-delà de 4 étapes.

```
/                    redirige : /offres si connecté, /connexion sinon
/connexion           saisie de l'adresse
/connexion/code      saisie du code (+ le nom, seulement si le compte est nouveau)
/offres              liste des offres — réservée aux connectés
/compte              adresse, nom, état, bouton « Se déconnecter »
```

### Le nom n'est demandé qu'aux comptes nouveaux, sans interroger l'API sur leur existence

`/auth/code/verifie` accepte `nom_complet` en option. Si le compte est nouveau et que le nom
manque, il lève `inscription_incomplete` **et redépose le code** (`src/api/routers/auth.py`,
commentaire : « l'utilisateur doit pouvoir corriger et resoumettre sans redemander un email,
attendre le cooldown et entamer son quota d'envois »). D'où :

- **Compte existant** : adresse → code → connecté. Deux écrans.
- **Compte nouveau** : adresse → code → `inscription_incomplete` → la même page réaffiche le
  champ code *et* un champ nom → connecté.

On ne demande donc jamais son nom à quelqu'un qui a déjà un compte, **sans jamais avoir demandé
à l'API si le compte existe**. La non-énumération des comptes est préservée intacte.

### L'adresse se reporte par cookie, jamais par l'URL

Entre l'écran 1 et l'écran 2, l'adresse doit survivre. Un `?adresse=…` l'inscrirait dans
l'historique du navigateur, dans l'en-tête `Referer` et dans les journaux de Next.

Cookie `jobbot_adresse_en_cours` : `httpOnly`, `SameSite=Lax`, `Secure` en production, durée de
vie 15 minutes (le code en vit 5 ; la marge couvre une correction de nom et une ressaisie).
Effacé dès la vérification réussie.

### Les erreurs remontent par redirection

Sans JS, `useActionState` n'existe pas. Une Server Action en échec redirige vers l'écran
d'origine avec `?erreur=<code>`, et la page rend la phrase correspondante. Le code d'erreur est
une valeur de la liste close du §4 ; toute valeur inconnue rend un message générique plutôt que
d'être affichée telle quelle.

---

## 6. Architecture du client

```
web/
├── app/
│   ├── layout.tsx              coquille, <html lang="fr">, feuille de style
│   ├── page.tsx                redirection selon la session
│   ├── connexion/
│   │   ├── page.tsx
│   │   ├── actions.ts          demanderCode()
│   │   └── code/
│   │       ├── page.tsx
│   │       └── actions.ts      verifierCode()
│   ├── offres/page.tsx
│   ├── compte/
│   │   ├── page.tsx
│   │   └── actions.ts          deconnecter()
│   ├── api-client.ts           LE SEUL module qui parle à l'API
│   ├── textes.ts               TOUS les textes utilisateur
│   ├── journal.ts              une ligne JSON par étape franchie
│   └── styles.css
├── Dockerfile
├── next.config.ts
├── package.json
├── tsconfig.json
└── mesure-poids.mjs
```

### `api-client.ts` — trois responsabilités, et pas une de plus

Aucun `fetch` ailleurs dans `web/`. C'est le pendant de « le LLM n'est appelé que depuis
`llm/client.py` » (§9).

1. **Transporter le cookie de session.** En lecture, lire `cookies()` et le repasser en en-tête
   `Cookie`. En écriture, reprendre le `Set-Cookie` de la réponse et le reposer via
   `cookies().set()`.
2. **Transmettre l'IP réelle** dans `X-Forwarded-For`.
3. **Traduire les codes d'erreur en exceptions typées**, jamais en phrases.

### Le piège des plafonds par IP

Les garde-fous anti-abus de l'API sont indexés sur l'IP (`auth_envois_par_ip_heure`,
`auth_verifications_par_ip_heure`). Next relayant tous les appels, **l'API verrait l'IP du
conteneur `web` pour tous les utilisateurs** : les compteurs s'effondrent en un seul seau, et
les premiers inscrits de l'heure bloquent tous les suivants. La panne serait silencieuse.

Le mécanisme de sortie existe déjà et `src/config.py` l'avait anticipé par écrit :

> « À renseigner le jour où un proxy existe : sans cela le plafond par IP compterait tous les
> utilisateurs ensemble ; avec une valeur trop large, n'importe qui pourrait usurper son IP. »

Donc, conjointement : `X-Forwarded-For` émis par `api-client.ts`,
`PROXY_IPS_DE_CONFIANCE` renseigné sur le réseau Compose, **et l'API rabattue sur `127.0.0.1`**
(§9). Les trois ou rien : `PROXY_IPS_DE_CONFIANCE` sans le rabattement du port rend l'usurpation
d'IP *plus* facile qu'aujourd'hui.

### `textes.ts`

Tous les textes destinés à l'utilisateur, vouvoyés, en français simple. Un objet dont les clés
couvrent les neuf codes d'erreur, plus les libellés d'écran. Vérifié par test (§8).

---

## 7. Le backend à écrire en plus

La liste des offres n'a rien en face : `src/api/routers/` ne porte que `sante`, `auth` et `moi`.

- **`src/api/routers/offres.py` — `GET /offres`**, authentifié par `deps.utilisateur_courant`,
  pagination par `limite` (défaut 20, plafond 50) et `decalage`. Pagination par décalage et non
  par curseur : à 232 lignes, un curseur serait de la complexité sans contrepartie, et l'index
  `ix_jobs_posted_at` existe déjà.
  **Tri : `posted_at` décroissant, `NULLS LAST`, puis `id` décroissant.** `jobs.posted_at` est
  nullable et Postgres place les `NULL` en tête sur un `DESC` : sans `NULLS LAST`, les offres
  sans date connue occuperaient la première page. Le second critère sur `id` rend l'ordre total,
  sans quoi deux pages successives peuvent répéter ou omettre une ligne.
- **`src/api/schemas/offres.py`** — projection explicite :
  `id, title, company, location, contract_type, posted_at, url, apply_method`.
  **Ni `description`, ni `raw`, ni `fingerprint`, ni `source_id`.** `description` pèse des
  kilooctets par offre et on est sous budget ; `raw` est la charge brute du scraper et n'a rien à
  faire chez un client.
- **Branchement de `rafraichir_si_necessaire()`** (`src/ingest/fraicheur.py`), écrit et testé le
  2026-09-08 et que rien n'appelle depuis. Une visite sur `/offres` déclenche au plus un
  rafraîchissement par source, protégé par son verrou Redis. La page étant réservée aux
  connectés, un visiteur anonyme ne peut pas s'en servir comme levier.

**Conséquence assumée : ce chantier n'est pas « juste le client web ».** C'est un écran web, un
endpoint API et un branchement d'ingestion.

---

## 8. Tests

- **`web/`, avec le lanceur intégré à Node (`node:test`)** — zéro dépendance ajoutée, donc rien à
  justifier au titre du §3. Couvre `api-client.ts` : transport du cookie, présence du
  `X-Forwarded-For`, correspondance des neuf codes d'erreur.
- **Un test Python lit `web/app/textes.ts`** et vérifie que chaque code de `src/core/erreurs.py`
  y a sa phrase. Seul garde-fou contre la dérive du jour où une dixième erreur apparaîtra côté
  Python : sans lui, l'utilisateur verrait un écran vide.
- **`GET /offres`** : 401 sans cookie, pagination, et surtout **absence de `description` et de
  `raw`** dans la réponse.
- **Le parcours de bout en bout est déroulé en vrai navigateur à la validation, pas automatisé.**
  L'automatiser demanderait Playwright en dépendance du dépôt pour un seul parcours.
- `mypy --strict` reste vert sur `src/` ; `tsc --noEmit` sur `web/`.

---

## 9. Déploiement

`web/Dockerfile` en multi-étapes (dépendances → build → exécution), `output: "standalone"` dans
`next.config.ts` pour que l'image finale ne porte pas les `node_modules` de build. Base
`node:24-alpine`. **Next 16.3.5, React 19.3.0** — versions relevées sur le registre npm le
2026-09-13, pas recopiées de mémoire.

Dans `docker-compose.yml` :

- retirer `profiles: ["web"]` : le service était déclaré en prévision, il devient réel ;
- publier `web` sur l'hôte, port `${WEB_HOST_PORT:-3000}` ;
- **rabattre `api` sur `127.0.0.1:${HTTP_PORT}`.** Le parcours `curl` du `README` continue de
  fonctionner en local ; l'API cesse d'être joignable de l'extérieur. Reprendre le style du
  commentaire déjà en place sur Postgres, qui dit explicitement de ne pas reproduire
  l'exposition sur le VPS ;
- `API_BASE_URL=http://api:${HTTP_PORT}` — et non une valeur en dur : `HTTP_PORT` est déjà
  configurable et `api` écoute dessus. Plus `PROXY_IPS_DE_CONFIANCE` réglé sur le réseau
  Compose. Les deux documentés dans `.env.example`.

---

## 10. Le poids, et comment on le mesure

`web/mesure-poids.mjs`, **sans dépendance** : charge la page d'inscription avec
`Accept-Encoding: gzip, br`, extrait les ressources référencées dans le HTML (`<script src>`,
`<link>`), les récupère compressées, additionne les octets transférés, et sort en échec au-delà
de 200 Ko.

**Limite assumée** : il ne verrait pas un fragment chargé dynamiquement. Avec zéro composant
client et aucun import dynamique, il n'y en a pas — si cela change, la mesure devient fausse
sans prévenir. La mesure est doublée **une fois**, à la validation, en vrai navigateur.

Budget prévisionnel : runtime Next ~90 Ko compressés (incompressible, il vient du framework),
HTML ~3 Ko, CSS ~4 Ko, police 0 Ko. Marge attendue : confortable, mais elle appartient au
framework, pas à nous.

---

## 11. Hors périmètre

PWA et service worker (Phase 4) ; recherche, filtres et tri des offres ; matching ; upload de
CV ; paiement ; espace admin. Aucune variable `NEXT_PUBLIC_*` : sans JS navigateur, rien n'a
besoin de traverser vers le client.

Le §11 du brief demande de **compter les abandons à chaque étape**. `journal.ts` émet une ligne
JSON par étape franchie sur la sortie standard, **sans adresse email** — juste l'étape. Assez
pour voir où le parcours perd des gens, pas assez pour constituer un fichier de données
personnelles.

---

## 12. Mises à jour du CLAUDE.md exigées par ce design

1. **§11** — « polices locales via `next/font` » devient la police système, avec la raison et la
   date.
2. **§4** — l'arborescence de `web/` passe de trois lignes à celle du §6 ci-dessus ; `src/api/`
   gagne `routers/offres.py` et `schemas/offres.py`.
3. **§12, Phase 2** — le critère 4 devient vérifiable, et la phase devient close quand il passe.

---

## 13. Ce que ce document ne tranche pas

- **§14.9, canal des alertes offres.** Toujours ouvert, et **bloque la Phase 4**. La liste des
  offres consultable ici n'y répond pas : consulter n'est pas être alerté. Ne pas en conclure
  que la question est réglée.
- **§14.1, nom de domaine.** Ne bloque pas ce chantier — le fournisseur d'email `console` suffit,
  le code sort dans les journaux du process `api`. Bloque la Phase 6.
- **§14.4, politique de confidentialité.** À trancher au plus tard en Phase 3.
