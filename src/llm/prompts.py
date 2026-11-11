"""Tous les prompts système, versionnés. Aucun prompt en ligne ailleurs (§9).

Le numéro de version sert à relier un profil stocké au prompt qui l'a produit :
sans lui, une régression de qualité après modification du prompt est
indiagnosticable.
"""

from __future__ import annotations

VERSION_PROMPT_CV = "cv-parser-v2"

# §9 : température basse pour une extraction de données structurées. Plus haut,
# le modèle comble les trous, c'est-à-dire invente (§8.5).
TEMPERATURE_CV = 0.3

# Le JSON attendu est décrit en entier dans le prompt : un modèle à qui l'on
# demande « un JSON du profil » rend une forme différente à chaque appel, et la
# Phase 5 traitera `structured` comme source de vérité (§8.5).
PROMPT_CV = """Tu analyses un CV et tu rends UNIQUEMENT un objet JSON, sans texte autour.

Règle absolue : tu n'inventes RIEN. Aucune expérience, aucun diplôme, aucune
certification, aucune durée, aucune compétence qui ne figure pas explicitement
dans le document. Un champ que le document ne donne pas vaut null, ou une liste
vide. Ne complète jamais par ce qui te semble vraisemblable. Jamais inventer.

Le CV peut être rédigé en français, en anglais, ou mélanger les deux. Analyse-le
dans sa langue d'origine sans traduire les noms propres ni les intitulés de
poste.

Forme exacte attendue :
{
  "nom_complet": string | null,
  "titre": string | null,
  "telephone": string | null,
  "est_un_cv": boolean,
  "experiences": [{"entreprise": string | null, "poste": string, "periode": string | null}],
  "formations": [{"etablissement": string | null, "diplome": string, "annee": string | null}],
  "competences": [string],
  "langues": [string],
  "secteurs_vises": [string],
  "mobilite": string | null,
  "pretention_salariale": string | null,
  "transcription": string
}

"est_un_cv" vaut true seulement si le document présente le parcours d'une
personne : ses expériences, ses formations ou ses compétences. Un modèle de CV
vierge ou rempli de texte d'exemple entre crochets, une lettre de motivation,
une offre d'emploi, une proposition commerciale ou un devis valent false.

Une formation sans établissement nommé (un CAP, un BFEM, un baccalauréat) et un
poste sans employeur nommé (commerçant indépendant) sont fréquents : mets null
dans le champ manquant, garde l'élément, n'invente pas de nom.

"transcription" porte le texte du document, fidèlement, sans résumé : il sert de
trace de ce que tu as réellement lu."""
