# JobBot Sénégal

Candidature assistée pour le marché de l'emploi sénégalais.
Voir `CLAUDE.md` pour le brief complet.

## Lancer l'API

Depuis un environnement disposant de son propre `.env` (voir `.env.example`) :

```bash
docker compose up -d --build
```

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
| `PROXY_IPS_DE_CONFIANCE` | Sans lui derrière un reverse proxy, le plafond par IP compte tous les utilisateurs ensemble ; avec une valeur trop large, l'IP devient usurpable |
| `POSTGRES_PASSWORD` explicite | `.env.example` est public et `src/config.py` a une valeur par défaut |
| `FOURNISSEUR_COURRIEL` autre que `console` | Sinon le démarrage échoue en `prod` — `console` écrit le code de vérification en clair dans les logs |
| `ADMIN_COURRIEL` | Sans lui, une alerte de scraper cassé ne part nulle part : elle reste dans les logs du VPS, à lire à la main |
| Reverse proxy devant `api` | Le service publie son port sur toutes les interfaces ; aucun proxy n'est déclaré dans `docker-compose.yml` |
| Nom de domaine + SPF/DKIM/DMARC | Aucun email réel ne part sans cela (§14.1) |
