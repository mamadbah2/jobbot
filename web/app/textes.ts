// TOUS les textes destinés à l'utilisateur. Aucun texte en clair dans un
// composant — convention héritée de `src/bot/texts.py`, qui survit au bot.
//
// Vouvoiement partout, français simple, aucun jargon RH (CLAUDE.md §11).

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
