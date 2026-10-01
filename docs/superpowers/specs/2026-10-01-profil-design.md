# Profil — design (Phase 3)

**Date :** 2026-10-01
**Décidé par :** le porteur du projet, en séance de conception
**Statut :** validé, à implémenter
**Précède :** la Phase 4 (matching et alertes), qui a besoin d'un profil pour comparer

---

## 1. Ce que la phase livre

L'utilisateur dépose son CV, le service en tire un profil structuré, l'utilisateur le corrige et
choisit ses préférences. C'est le premier endroit où le produit appelle un LLM, et le premier où il
stocke des données personnelles lourdes.

C'est aussi l'échéance que le brief fixe lui-même au §14.4 et §14.7 : **la politique de
confidentialité et la suppression des données sur demande arrivent dans cette phase**, parce que
c'est celle qui commence à stocker des CV.

---

## 2. Décisions prises en séance

| Question | Décision | Raison |
|---|---|---|
| Attente pendant l'analyse | **Arrière-plan**, écran rechargé par balise HTML | Une requête qui tient 30 s sur une 3G instable tombe, et l'utilisateur a payé l'envoi pour rien |
| Où tourne l'analyse | **Dans le process `api`**, état en Postgres | Motif déjà en place pour le rafraîchissement des offres, pièges déjà payés. Un cinquième process serait de la sur-ingénierie (§2.5) |
| Fichier d'origine | **Jamais conservé** | La Phase 5 génère depuis le profil, elle n'a jamais besoin de l'original. Supprime d'un coup le stockage de fichiers, les CV dans les sauvegardes, et l'essentiel du risque de fuite |
| `profiles.cv_file_path` | **Supprimée** | Resterait vide à jamais ; une colonne qui promet un fichier qu'on ne stocke pas est un piège pour une session future |
| Édition du profil | **Champs simples modifiables, listes en lecture** | Sans JavaScript, chaque ligne ajoutée coûte un aller-retour payé en data. Un formulaire d'expériences complet est l'écran où l'on abandonne (§11) |
| CV photo (JPEG/PNG) | **Accepté**, lu par `deepseek-flash` en multimodal | Cas courant au Sénégal, et il se ferme sans aucune dépendance nouvelle |
| PDF scanné | **Refusé**, message clair | Le rastériser demanderait poppler et du calcul sur un VPS à 5 € |
| Modèle | **`deepseek-flash`**, configurable | ~0,7 FCFA par CV contre ~2,6 pour `deepseek-v4-pro`. On monte seulement si la qualité l'exige, sur mesure |

### Une décision révisée en cours de séance, et pourquoi

Le refus des CV en image avait d'abord été retenu, au motif que l'OCR imposerait une dépendance
lourde, de la mémoire et du calcul sur le VPS, pour une qualité médiocre. **Relevé le 2026-10-01
sur l'API : `deepseek-flash` accepte nativement les images** (`input_modalities: ["text","image"]`,
vérifié en appelant `/models`, pas lu dans une doc). Les trois coûts qui motivaient le refus
disparaissent : même SDK, même client, même modèle, et le calcul se fait chez DeepSeek.

La décision a donc été reprise. `deepseek-v4-pro` est en revanche **texte seulement** : si la
qualité du parsing nous poussait un jour vers lui, le chemin image devrait rester sur `flash`.

---

## 3. Contraintes héritées, non négociables

- **Aucun composant client** (`'use client'`) côté web. Les écrans fonctionnent sans JavaScript.
- **Aucun texte utilisateur hors de `web/app/textes.ts`.** Vouvoiement, français simple, aucun
  jargon RH.
- **Le poids transféré reste un critère de phase** : référence actuelle 133 Ko sur `/connexion`,
  plafond 200 Ko. Les nouveaux écrans se mesurent avec `web/mesure-poids.mjs`.
- **Aucune dépendance sans justification écrite** (§3).
- **Coût LLM par candidature < 15 FCFA** (§9), coût de chaque appel journalisé dans
  `usage_counters`.
- **Prompts versionnés dans `llm/prompts.py`**, aucun prompt en ligne. Client unique dans
  `llm/client.py`, aucun appel ailleurs.
- **La base de développement est partagée** et porte 314 offres réelles. Jamais de
  `docker compose down -v`, jamais d'`alembic downgrade`.

---

## 4. La règle la plus importante de cette phase

**Le texte d'un CV ne doit jamais atteindre un journal, un message d'exception, ou une alerte
admin.**

C'est la donnée la plus sensible que le produit manipulera : nom, adresse, parcours, parfois
situation familiale ou religion. Le dépôt porte déjà `tests/test_logs_sans_pii.py` et
`tests/test_logs_sans_pii_uvicorn_reel.py` ; cette phase les étend au CV.

Le §7 du brief avertit déjà que `AlerteCourriel` recopie **tout son contexte** dans un message qui
part par le réseau, et que `erreur=str(exc)` est son champ libre à surveiller. Une exception levée
par la couche LLM ou par l'extraction de texte **peut contenir un fragment de CV**. Toute alerte
émise par cette phase ne transporte donc que des identifiants et des codes, jamais de contenu.

---

## 5. Données

`profiles` existe depuis la Phase 0 : `user_id`, `raw_cv_text`, `structured`, `cv_file_path`,
`updated_at`. Une migration Alembic :

**Ajoute**

| Colonne | Forme | Rôle |
|---|---|---|
| `parse_etat` | `VARCHAR(16)` + `CHECK` | `en_attente` / `en_cours` / `pret` / `echec` |
| `parse_erreur` | `VARCHAR(64)`, nullable | Code d'échec stable, **jamais une phrase** — les textes vivent chez le client |
| `parse_demarre_le` | `TIMESTAMPTZ`, nullable | Rend inutile tout balayeur de tâches zombies (§7) |

`VARCHAR` + `CHECK` et non un ENUM natif : le §5 l'exige, ajouter une valeur à un ENUM impose une
migration bloquante.

**Supprime** `cv_file_path`. La colonne est vide partout (aucun code ne l'a jamais écrite) ; la
suppression ne perd donc aucune donnée.

### Ce qui est stocké après cette phase, et rien d'autre

`users.email`, `users.full_name`, `profiles.raw_cv_text`, `profiles.structured`. Pas de fichier.

`structured` est la **source de vérité** du post-contrôle anti-invention de la Phase 5 (§8.5) : tout
diplôme ou entreprise cité dans une lettre devra y figurer. Sa forme compte donc au-delà de cette
phase : `experiences`, `formations`, `competences`, `langues`, `secteurs_vises`, `mobilite`,
`pretention_salariale`, plus les champs d'identité que le CV porte (`nom_complet`, `titre`,
`telephone`). Le §5 du brief prévoit explicitement que le numéro de téléphone réapparaisse ici,
sans unicité et sans valeur d'identité.

---

## 6. Le parcours

Un écran, `/profil`, qui rend ce que l'état commande.

| État | Ce que l'utilisateur voit |
|---|---|
| pas de profil | le formulaire de dépôt |
| `en_cours` | écran d'attente, rechargé par `<meta http-equiv="refresh">`, zéro JavaScript |
| `en_cours` depuis plus de `CV_ANALYSE_DELAI_MAX_SECONDES` | traité comme `echec` **à l'affichage** |
| `pret` | le profil extrait, champs simples modifiables, préférences |
| `echec` | ce qui n'a pas marché, en français simple, et le bouton pour redéposer |

**Les corrections et les préférences partent dans la même soumission.** Le §6 en fait deux étapes ;
les fusionner en épargne une, et chaque étape coûte des abandons (§11) et un aller-retour payé en
data. Le §6 du brief est à mettre à jour en conséquence.

**Les préférences sont des boutons, aucune saisie libre** — lettre du §6 : secteurs, région, type
de contrat.

**Pas de balayeur de tâches zombies.** Si `api` redémarre en pleine analyse, le profil reste
`en_cours` : passé `CV_ANALYSE_DELAI_MAX_SECONDES`, l'écran le présente comme un échec et propose de
redéposer. Rien à faire tourner, donc rien à déboguer un jour de panne.

---

## 7. L'API

```
POST   /profil/cv    dépôt du fichier — limite de taille propre à cette route
GET    /profil       le profil et son état
PUT    /profil       corrections + préférences, en une soumission
DELETE /moi          « supprimer mes données » (§14.4)
```

### `POST /profil/cv` — tout ce qui peut être refusé l'est avant de payer un token

Dans la requête, sans rien attendre du réseau :

1. **Taille** vérifiée avant de lire le contenu, pas après.
2. **Type réel** reconnu aux octets de tête, pas à l'extension : PDF (`%PDF`), DOCX (archive ZIP),
   JPEG (`FF D8 FF`), PNG (`89 50 4E 47`). Une extension ne prouve rien.
3. **Plafond d'analyses du jour** (§10 ci-dessous) : refusé avant tout travail.
4. Selon le type :
   - **PDF ou DOCX** → extraction du texte, localement, en quelques dizaines de millisecondes.
     **Si le texte extrait fait moins de `CV_TEXTE_MIN_CARACTERES` signes** (défaut **200**, hors
     espaces), refus immédiat avec le code `cv_sans_texte` : c'est là que le PDF scanné est écarté,
     **sans qu'un seul token soit payé**. Le seuil est explicite et configurable parce qu'un PDF
     scanné rend rarement zéro caractère — il rend souvent quelques artefacts de police, et « vide »
     ne serait donc pas un test suffisant.
   - **JPEG ou PNG** → aucune extraction possible localement. Voir §8.

Ce n'est qu'après ce filtre que l'état passe à `en_cours`, que l'analyse de fond est lancée, et que
la route rend un `202`.

### `DELETE /moi`

Ce n'est pas un bonus : c'est le §14.4, dont le brief fixe l'échéance à cette phase. La cascade
existe déjà dans le modèle (`ondelete="CASCADE"` sur `profiles.user_id`). L'action est exposée dans
`/compte`, derrière une confirmation explicite — c'est irréversible.

Le cookie de session doit être effacé dans la même réponse : laisser un jeton valide pointer vers
un compte supprimé enverrait l'utilisateur sur un 401 inexpliqué au prochain écran, au lieu de la
page de connexion.

### Deux plafonds de corps à relever, et à borner

- L'API porte un **plafond global de 64 Ko** (`src/api/app.py`), dont le commentaire annonce déjà
  qu'« l'upload de CV de la Phase 3 aura sa propre limite, plus haute, propre à sa route ».
- Les **Server Actions de Next plafonnent à 1 Mo** par défaut, en dessous de beaucoup de PDF et de
  toutes les photos.

Les deux se relèvent à `CV_TAILLE_MAX_MO` (défaut **5**), et pas davantage : un plafond relevé sans
borne est une porte ouverte.

---

## 8. Le chemin image, et la seule donnée qui transite

Une photo n'a **pas de texte à extraire localement**. Elle doit donc survivre entre la requête de
dépôt et la tâche de fond qui appellera DeepSeek.

**Elle vit en Redis, avec un TTL court, consommée une fois puis supprimée.** Jamais sur disque,
jamais dans Postgres — donc **jamais dans une sauvegarde**. C'est le même régime que le code de
vérification (§2, interdiction n°2), et pour la même raison : ce qui ne doit pas durer ne doit pas
atteindre une base.

Conséquences assumées :

- Redis est en mémoire sur un VPS à 5 €. Le plafond de taille (5 Mo) et le plafond d'analyses
  journalier bornent l'occupation. Le TTL (`CV_IMAGE_TTL_SECONDES`, défaut 600) garantit qu'une
  tâche perdue ne laisse rien derrière elle.
- Si le TTL expire avant que la tâche ne consomme l'image, l'état passe à `echec` avec un code
  propre, et l'utilisateur redépose. Pas de reprise à écrire.

**Les deux chemins convergent.** Le prompt du parsing demande, en une seule réponse, le profil
structuré **et** une transcription fidèle du CV. Après analyse, une photo et un PDF ont donc rempli
exactement les mêmes colonnes : `raw_cv_text` et `structured`. Rien dans la suite du produit n'a
besoin de savoir par quel chemin le profil est arrivé.

---

## 9. La couche LLM

### Modèles et tarifs — relevés, pas supposés

Le §9 du brief dit « utiliser `deepseek-chat` » et, dans la même phrase, de vérifier les noms en
cours plutôt que de se fier à une valeur en dur. **Vérification faite le 2026-10-01 contre
`/models` : `deepseek-chat` n'existe plus.** Les deux modèles disponibles sont :

| Modèle | Entrées | Contexte |
|---|---|---|
| `deepseek-flash` (DeepSeek-V4.1-Flash) | texte **et image** | 1 048 576 |
| `deepseek-v4-pro` (DeepSeek-V4-Pro) | texte seulement | 1 048 576 |

Tarifs relevés le même jour, par million de tokens, en dollars :

| | entrée (cache touché) | entrée (cache manqué) | sortie |
|---|---|---|---|
| `deepseek-flash` hors pointe | 0,003 | 0,15 | 0,6 |
| `deepseek-flash` en pointe | 0,006 | 0,3 | 1,2 |
| `deepseek-v4-pro` hors pointe | 0,022 | 0,66 | 1,98 |
| `deepseek-v4-pro` en pointe | 0,044 | 1,32 | 3,96 |

Heures de pointe : 01:00–04:00 et 06:00–10:00 UTC, du lundi au vendredi.

**Le §9 du brief est donc à corriger**, et ces chiffres sont eux-mêmes datés : ils se revérifient,
ils ne se recopient pas.

### Deux pièges de facturation qui fausseraient le suivi de coût

1. **L'entrée servie par le cache coûte 50 fois moins** que l'entrée manquée (0,003 contre 0,15).
   Un calcul qui confond les deux se trompe massivement. La réponse de l'API donne le détail : on
   s'en sert plutôt que de multiplier un total par un tarif moyen.
2. **Le tarif de pointe double tout.** Un coût calculé sans regarder l'heure se trompe du simple au
   double selon le moment de la journée.

Le cache de contexte que le §9 recommande n'a **rien à cacher ici** : chaque CV est différent. Il
prendra son sens en Phase 5, où le profil est identique d'une candidature à l'autre.

### Estimation de coût, à confirmer par la mesure

Un CV représente de l'ordre de 2 000 tokens en entrée et 1 500 en sortie, soit **environ 0,7 FCFA
avec `deepseek-flash`** et **2,6 FCFA avec `deepseek-v4-pro`** — tous deux très loin sous le
plafond de 15 FCFA du §9. Une image consomme davantage de tokens d'entrée qu'un texte : à mesurer
dès les premiers essais, pas à supposer.

### Forme du client

`llm/client.py`, unique, SDK `openai` pointé sur `https://api.deepseek.com`. Relance avec attente
exponentielle sur 429 et 5xx, délai maximal 60 s, et **repli explicite** : si DeepSeek est
indisponible, l'état passe à `echec`, le message est clair, et **le quota d'analyses n'est pas
décompté**. Jamais de plantage silencieux (§9).

`llm/prompts.py` porte le prompt de parsing avec un **numéro de version en constante**. Température
0,3 (§9). Sortie JSON, lecture défensive : nettoyage des clôtures ``` avant `json.loads`, une
relance en cas d'échec.

`llm/cv_parser.py` ne fait qu'une chose : texte ou image → profil structuré + transcription.

### Les réglages introduits par cette phase

| Variable | Défaut | Rôle |
|---|---|---|
| `DEEPSEEK_API_KEY` | — | Déjà dans le `.env` local, mais **absente de `Settings`** : `extra="ignore"` l'avale en silence aujourd'hui |
| `DEEPSEEK_MODELE` | `deepseek-flash` | Permet de monter vers `deepseek-v4-pro` sans redéploiement de code |
| `CV_TAILLE_MAX_MO` | 5 | Borne le corps accepté, côté API **et** côté Server Action Next |
| `CV_TEXTE_MIN_CARACTERES` | 200 | En dessous, le document est traité comme non textuel |
| `CV_ANALYSES_PAR_JOUR` | 5 | Plafond anti-abus, et plafond de coût |
| `CV_IMAGE_TTL_SECONDES` | 600 | Durée de vie de l'image en Redis |
| `CV_ANALYSE_DELAI_MAX_SECONDES` | 300 | Au-delà, une analyse `en_cours` est présentée comme échouée |

---

## 10. Garde-fous

**Plafond d'analyses par utilisateur et par jour** (`CV_ANALYSES_PAR_JOUR`, défaut 5). Chaque
analyse coûte de l'argent réel : sans plafond, une boucle de redépôt vide la marge. La mécanique
Redis de `src/core/auth/limites.py` est réutilisée plutôt que réinventée.

**Taille et type** : bornés avant lecture, reconnus aux octets de tête (§7).

**Aucun contenu de CV dans un journal, une exception ou une alerte** (§4 de ce document).

**Le profil appartient à son propriétaire** : `GET /profil`, `PUT /profil` et `POST /profil/cv`
passent tous par `deps.utilisateur_courant` et ne lisent jamais un `user_id` venu de la requête.

---

## 11. Confidentialité (§14.4 et §14.7)

**Ce que le service stocke** après cette phase : adresse email, nom, texte du CV, profil structuré.
Aucun fichier d'origine.

**Durée de conservation** : tant que le compte existe. `DELETE /moi` supprime tout, immédiatement.

**Un fait que la politique doit dire, et qui n'est pas une formalité : le contenu du CV est envoyé
à DeepSeek**, donc à un tiers, hors du Sénégal. C'est le genre de chose qu'un utilisateur a le
droit de savoir **avant** de déposer son CV, pas après — l'information apparaît donc sur l'écran de
dépôt, pas seulement dans une page de politique que personne n'ouvre.

**Ce que cette phase livre** : la mécanique de suppression, et une page qui décrit **exactement ce
que le système fait** — ce qui est collecté, pourquoi, où ça va, combien de temps, comment
supprimer. C'est une description de comportement, vérifiable contre le code.

**Ce que cette phase ne livre pas** : le texte juridique. Un engagement de confidentialité engage
le porteur du projet, pas l'outil qui l'écrit. La page porte la description factuelle ; la
formulation juridique est à fournir, et c'est un point ouvert nommé au §14 ci-dessous.

---

## 12. Tests

- **Extraction de texte** : un PDF et un DOCX figés dans `tests/fixtures/`, plus un PDF **sans
  texte** qui doit être refusé avec `cv_sans_texte` **sans aucun appel LLM** — vérifié par un
  double qui échouerait s'il était appelé.
- **Reconnaissance de type aux octets de tête** : un fichier renommé en `.pdf` qui n'en est pas.
- **Plafond d'analyses journalier** : le §13 exige un test pour toute règle de quota.
- **Calcul de coût** : cache touché contre manqué, heure de pointe contre heure creuse. C'est une
  règle de facturation, elle se teste comme un quota.
- **Lecture défensive du JSON** : clôtures ``` présentes, JSON invalide puis valide à la relance.
- **Aucun contenu de CV dans les journaux** : extension des deux tests existants.
- **Cycle d'états** : `en_attente` → `en_cours` → `pret`, et `en_cours` périmé présenté comme
  `echec`.
- **`DELETE /moi`** : le profil disparaît, et une seconde connexion avec la même adresse crée bien
  un compte neuf.
- **Aucun test unitaire ne touche le réseau ni la base** : le client DeepSeek est injectable, comme
  le fournisseur de courriel l'est déjà.

**Le critère de validation de la phase — « 10 CV réels de formats différents parsés correctement »
— demande dix vrais CV, que le dépôt n'a pas.** Des fichiers synthétiques ne valideraient rien : ce
que le critère mesure, c'est la résistance aux mises en page réelles, colonnes, tableaux, polices
inhabituelles. Ils sont à fournir par le porteur du projet, anonymisés ou non. **Point ouvert
nommé au §14.**

---

## 13. Hors périmètre

Matching et alertes (Phase 4), génération de CV adapté et de lettre (Phase 5), quotas de
candidatures (Phase 5), paiement (Phase 6), PWA et service worker (Phase 4, rendus obligatoires
par le choix du push — §14.9).

Pas de PDF scanné rastérisé. Pas d'OCR local. Pas d'édition des expériences et formations.

---

## 14. Mises à jour du CLAUDE.md exigées par ce design

1. **§9** — `deepseek-chat` remplacé par `deepseek-flash` et `deepseek-v4-pro`, avec la grille de
   tarifs datée, la mention des deux pièges de facturation, et le fait que `flash` lit les images.
2. **§3** — dépendances ajoutées : `openai`, `pdfplumber`, `python-docx`, avec leur justification.
3. **§5** — `cv_file_path` supprimée ; `parse_etat`, `parse_erreur`, `parse_demarre_le` ajoutées ;
   la raison de ne pas conserver le fichier.
4. **§4** — arborescence : `src/llm/` cesse d'être un package vide, `src/api/routers/profil.py`,
   `src/api/schemas/profil.py`, les écrans web du profil.
5. **§6** — étapes 2 et 3 de l'onboarding fusionnées en une soumission, et pourquoi.
6. **§14.4 et §14.7** — tranchés : pas de conservation du fichier, suppression immédiate sur
   demande, transfert à DeepSeek annoncé sur l'écran de dépôt. Reste ouvert : le texte juridique.
7. **§12, Phase 3** — critère de validation précisé : les dix CV réels sont une fourniture du
   porteur du projet, pas un livrable du code.

---

## 15. Ce que ce document ne tranche pas

- **Le texte juridique de la politique de confidentialité.** La description factuelle est livrée ;
  la formulation qui engage le porteur du projet lui appartient.
- **Les dix CV réels** du critère de validation. L'implémentation n'en dépend pas, la validation
  de la phase si.
- **§14.8** — canal du repli de paiement manuel. Toujours ouvert, bloque la **Phase 6**.
- **§14.10** — comportement au-delà de 15 candidatures pour une même offre. Toujours ouvert,
  bloque la **Phase 5**.
