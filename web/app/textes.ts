// TOUS les textes destinés à l'utilisateur. Aucun texte en clair dans un
// composant — convention héritée de `src/bot/texts.py`, qui survit au bot.
//
// Vouvoiement partout, français simple, aucun jargon RH (CLAUDE.md §11).

/** Les codes d'erreur que l'API peut renvoyer. Liste FERMÉE, et c'est ce qui
 *  la rend utile : `journal.ts` s'en sert pour que seul un de ces littéraux
 *  puisse entrer dans les journaux, ce qui interdit à la compilation d'y
 *  glisser un texte libre — et avec lui une adresse email.
 *
 *  Un test vérifie que cette liste et `ERREURS` ci-dessous ne divergent pas. */
export const CODES_ERREUR = [
  'adresse_invalide',
  'trop_de_demandes',
  'plafond_global_atteint',
  'envoi_impossible',
  'code_invalide',
  'code_expire',
  'inscription_incomplete',
  'nom_invalide',
  'jeton_invalide',
  'cv_type_refuse',
  'cv_trop_gros',
  'cv_sans_texte',
  'cv_illisible',
  'trop_d_analyses',
  'analyse_indisponible',
  'profil_absent',
  'analyse_interrompue',
  'image_expiree',
  'analyse_echouee',
  'erreur_metier',
  'defaut',
] as const

export type CodeErreur = (typeof CODES_ERREUR)[number]

export const ERREURS: Record<string, string> = {
  adresse_invalide: "Cette adresse email ne semble pas valide. Vérifiez-la et réessayez.",
  trop_de_demandes: "Vous avez fait trop d'essais. Patientez un moment avant de recommencer.",
  plafond_global_atteint:
    "Le service reçoit trop de demandes en ce moment. Réessayez dans quelques minutes.",
  envoi_impossible:
    "Nous n'arrivons pas à envoyer le code pour l'instant. Réessayez dans quelques minutes.",
  code_invalide: "Ce code n'est pas le bon. Vérifiez votre email et ressaisissez-le.",
  code_expire: "Ce code a expiré. Demandez-en un nouveau.",
  inscription_incomplete: "Il nous manque votre nom pour créer votre compte.",
  nom_invalide: "Ce nom ne semble pas valide. Utilisez votre prénom et votre nom.",
  jeton_invalide: "Votre session a expiré. Reconnectez-vous.",
  cv_type_refuse: "Nous acceptons les fichiers PDF, Word, ou une photo de votre CV.",
  cv_trop_gros: "Ce fichier est trop lourd. Essayez un fichier de moins de 5 Mo.",
  cv_sans_texte:
    "Nous n'avons pas réussi à lire le texte de ce document. S'il s'agit d'un scan, envoyez plutôt une photo de votre CV.",
  cv_illisible: "Ce fichier n'a pas pu être ouvert. Vérifiez qu'il n'est pas protégé par un mot de passe.",
  trop_d_analyses: "Vous avez déjà analysé plusieurs CV aujourd'hui. Revenez demain.",
  analyse_indisponible: "L'analyse n'est pas disponible pour le moment. Réessayez dans quelques minutes.",
  profil_absent: "Déposez d'abord votre CV.",
  // Ces trois-là ne sont pas des exceptions Python : ils viennent de
  // `parse_erreur`, écrit par la tâche d'analyse en arrière-plan.
  analyse_interrompue: "L'analyse n'a pas abouti. Déposez à nouveau votre CV.",
  image_expiree: "L'analyse a pris trop de temps. Déposez à nouveau votre CV.",
  analyse_echouee: "Nous n'avons pas réussi à analyser ce CV. Déposez-en un autre.",
  erreur_metier: "Une erreur est survenue. Réessayez.",
  defaut: "Une erreur est survenue. Réessayez.",
}

export function texteErreur(code: string | undefined): string | null {
  if (!code) return null
  return ERREURS[code] ?? ERREURS.defaut
}

export const T = {
  titreAdresse: 'Votre adresse email',
  aideAdresse: "Nous vous envoyons un code à 6 chiffres. Il n'y a pas de mot de passe.",
  champAdresse: 'Adresse email',
  boutonAdresse: 'Recevoir mon code',

  titreCode: 'Votre code',
  aideCode: 'Saisissez le code à 6 chiffres que vous venez de recevoir.',
  champCode: 'Code à 6 chiffres',
  champNom: 'Votre prénom et votre nom',
  aideNom: "C'est votre première connexion : indiquez-nous votre nom.",
  boutonCode: 'Continuer',
  retourConnexion: 'Utiliser une autre adresse email',

  titreOffres: "Offres d'emploi",
  aucuneOffre: "Aucune offre pour le moment. Revenez un peu plus tard.",
  voirOffre: "Voir l'offre",
  lienIndisponible: 'Lien indisponible pour cette offre',
  parEmail: 'Candidature par email',
  parFormulaire: 'Candidature sur le site',
  parSiteExterne: 'Candidature sur un autre site',
  pageInexistante: "Cette page n'existe pas.",
  revenirPremierePage: 'Revenir à la première page',
  pagePrecedente: 'Page précédente',
  pageSuivante: 'Page suivante',

  titreCompte: 'Votre compte',
  boutonDeconnexion: 'Se déconnecter',
  lienOffres: 'Les offres',
  lienCompte: 'Mon compte',

  titreProfil: 'Votre CV',
  aideDepot: "Déposez votre CV en PDF, en Word, ou prenez-en une photo.",
  // Sur l'écran de DÉPÔT, pas seulement dans une page de politique : un
  // utilisateur a le droit de savoir, avant de confier son CV, qu'il part chez
  // un tiers hors du Sénégal.
  avertissementDeepSeek:
    "Pour lire votre CV, nous l'envoyons à notre prestataire d'analyse, hors du Sénégal. Rien n'est conservé de votre fichier d'origine.",
  champFichier: 'Votre CV',
  boutonDeposer: 'Analyser mon CV',
  analyseEnCours: "Nous lisons votre CV. Cette page se met à jour toute seule.",
  titreValidation: 'Vérifiez votre profil',
  aideValidation: "Corrigez ce qui est faux, puis choisissez ce que vous cherchez.",
  boutonValider: 'Enregistrer',
  redeposerCv: 'Déposer un autre CV',
  lienProfil: 'Mon CV',
  lienConfidentialite: 'Vos données',
  titreSuppression: 'Supprimer mes données',
  aideSuppression:
    "Votre compte, votre CV et votre profil seront supprimés immédiatement. C'est définitif.",
  boutonSupprimer: 'Supprimer définitivement mes données',
  champNomProfil: 'Votre nom',
  champTitre: 'Le poste que vous cherchez',
  champCompetences: 'Vos compétences, séparées par des virgules',
  champLangues: 'Vos langues, séparées par des virgules',
  legendeSecteurs: 'Les secteurs qui vous intéressent',
  champRegion: 'Où cherchez-vous ?',
  champContrat: 'Quel type de contrat ?',
  titreLecture: 'Ce que nous avons lu dans votre CV',
  aucuneLecture: 'Aucune expérience ni formation détectée.',
  siFaux: "Si c'est faux,",

  // Panne réseau ou serveur pendant le chargement d'un écran (§11 : toujours
  // une sortie, même quand tout casse). On dit quoi faire, jamais ce qui a
  // cassé.
  erreurTemporaire: "Nous n'arrivons pas à charger cette page pour le moment. Réessayez.",
  reessayer: 'Réessayer',

  // Adresse inexistante. Sans cet écran, Next sert son 404 d'usine, en
  // anglais et sans lien de sortie.
  titreIntrouvable: 'Page introuvable',
  aideIntrouvable: "Le lien que vous avez suivi ne mène à rien. Il a peut-être changé.",
  retourAccueil: "Revenir à l'accueil",
}

/** Libellés des valeurs de `users.state` — la liste fait foi dans
 *  `USER_STATES` (src/db/models.py), pas ici.
 *
 *  On affiche une phrase, jamais la valeur brute « active » : c'est un
 *  identifiant technique, pas du français, et le §11 proscrit le jargon.
 *
 *  Le repli n'est pas de la prudence gratuite : la colonne est un
 *  `VARCHAR` + `CHECK` précisément pour pouvoir gagner une valeur sans
 *  migration bloquante (§5). Le jour où cela arrive, l'écran doit dire
 *  quelque chose plutôt que rien. */
const ETATS: Record<string, string> = {
  onboarding: 'Inscription en cours',
  active: 'Compte actif',
  blocked: 'Compte suspendu',
}

export function etatLisible(etat: string): string {
  return ETATS[etat] ?? 'État inconnu'
}

/** Choix proposés sur l'écran de profil : des boutons, jamais de saisie
 *  libre (§6). Ici et non dans la page, car ce sont des libellés affichés. */
export const SECTEURS = [
  'Comptabilité et finance',
  'Informatique',
  'Commerce et vente',
  'Santé',
  'Éducation',
  'Logistique et transport',
  'Bâtiment',
  'Humanitaire et ONG',
]
export const REGIONS = ['Dakar', 'Thiès', 'Saint-Louis', 'Ziguinchor', 'Kaolack', 'Tout le Sénégal']
export const CONTRATS = ['CDI', 'CDD', 'Stage', 'Freelance']
