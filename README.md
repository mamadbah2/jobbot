# JobBot Sénégal

Candidature assistée pour le marché de l'emploi sénégalais.
Voir `CLAUDE.md` pour le brief complet.

## Lancer le tout

```bash
docker compose up -d --build
```

Cinq services démarrent. Le seul que vous ouvrez dans un navigateur est le
client web :

| Service | Adresse | Rôle |
|---|---|---|
| `web` | <http://localhost:3000> | **L'interface. C'est par là qu'on entre.** |
| `api` | `127.0.0.1:8080` | Backend REST, boucle locale seulement |
| `postgres` | `127.0.0.1:55432` | Base, boucle locale seulement |
| `redis` | interne | Codes de vérification, verrous, plafonds |
| `worker_ingest` / `worker_match` | interne | Scraping et matching |

### Le parcours, dans le navigateur

1. Ouvrez <http://localhost:3000>. Vous êtes renvoyé vers `/connexion`.
2. Saisissez une adresse email. **Aucun email réel ne part** tant qu'aucun
   nom de domaine n'existe (`CLAUDE.md` §14.1) : le fournisseur `console`
   écrit le code dans les logs.
3. Lisez le code :
   ```bash
   docker compose logs api --since 1m | grep courriel_non_envoye_mode_console
   ```
4. Saisissez ce code, puis votre nom à la première connexion. Vous arrivez sur
   la liste des offres. `/compte` affiche vos informations et le bouton de
   déconnexion.

> `web` n'est PAS derrière un reverse proxy et le sait : `WEB_DERRIERE_PROXY`
> vaut `false`, donc aucun `X-Forwarded-For` n'est transmis à l'API, et les
> plafonds « par IP » se comportent en pratique comme des plafonds globaux.
> C'est documenté et assumé — voir `.env.example`, et §14.1 pour la Phase 6.

### Développer le client web

```bash
cd web
npm install
npm run dev        # serveur de développement, port 3000
npm test           # tests unitaires (node --test), sans argument
npm run typecheck  # tsc --noEmit
npm run mesure     # poids transféré de /connexion, plafond 200 Ko (§11)
```

## Parcours d'API en ligne de commande

L'équivalent du parcours ci-dessus sans navigateur, utile pour déboguer l'API
seule. `api` n'écoute que sur la boucle locale : le navigateur passe toujours
par `web`, jamais directement par elle.

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

Les étapes 1 à 6 couvrent les critères de validation 1 à 3 de la Phase 2 (`CLAUDE.md` §12).

> L'équivalent automatisé de ce parcours (demande → vérification → session → déconnexion)
> est couvert par les tests d'intégration : `RUN_INTEGRATION_TESTS=1 pytest -m integration`.

## Liste de contrôle avant mise en production

Chaque ligne est un garde-fou déjà codé, mais **inopérant s'il est oublié** au moment
du déploiement : rien ici ne s'active tout seul.

| À poser avant d'ouvrir au public | Pourquoi |
|---|---|
| `ENVIRONMENT=prod` | Sans lui, aucun secret JWT n'est exigé et le cookie de session perd son drapeau `Secure` |
| `JWT_SECRET` d'au moins 32 caractères | Sinon le démarrage échoue en `prod` — c'est voulu |
| `PROXY_IPS_DE_CONFIANCE` **et** `WEB_DERRIERE_PROXY` | Les deux ou aucun. Sans eux, le plafond par IP compte tous les utilisateurs ensemble ; avec l'un des deux seulement, ou avec une valeur trop large, l'IP devient usurpable et le plafond ne vaut plus rien |
| `POSTGRES_PASSWORD` explicite | `.env.example` est public et `src/config.py` a une valeur par défaut — **la même** : `jobbot_dev_password`, publiée dans les deux fichiers |
| `FOURNISSEUR_COURRIEL` autre que `console` | Sinon le démarrage échoue en `prod` — `console` écrit le code de vérification en clair dans les logs |
| `ADMIN_COURRIEL` | Sans lui, une alerte de scraper cassé ne part nulle part : elle reste dans les logs du VPS, à lire à la main |
| Reverse proxy **avec TLS** devant `web` | `web` est publié en direct sur toutes les interfaces et aucun proxy n'est déclaré dans `docker-compose.yml`. Sans TLS, `ENVIRONMENT=prod` pose `secure: true` sur le cookie de session et le navigateur le jette : la connexion échoue **sans aucune erreur serveur** |
| Nom de domaine + SPF/DKIM/DMARC | Aucun email réel ne part sans cela (§14.1) |
