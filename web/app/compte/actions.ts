'use server'

import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

import { ErreurApi, NOM_COOKIE } from '../api-contrat'
import { deconnecter, supprimerMesDonnees } from '../api-client'
import { journaliser } from '../journal'

export async function seDeconnecter(): Promise<void> {
  try {
    await deconnecter()
  } catch (erreur) {
    // Une session déjà invalide n'empêche pas de se déconnecter : c'est
    // exactement ce que l'utilisateur demande.
    if (!(erreur instanceof ErreurApi)) throw erreur
  }

  // L'API efface son cookie, mais c'est nous qui l'avons posé : il faut
  // l'effacer ici aussi. La révocation réelle tient à `token_version` côté
  // base, pas à la disparition du cookie.
  // `path` explicite plutôt qu'implicite : un navigateur n'efface un cookie
  // que si les attributs correspondent à ceux posés (`attributsCookieSession`,
  // `path: '/'`) — c'est le défaut qui avait mordu `delete_cookie` côté
  // Python en Phase 2.
  const magasin = await cookies()
  magasin.delete({ name: NOM_COOKIE, path: '/' })

  journaliser('deconnexion')
  redirect('/connexion')
}

export async function supprimerMonCompte(): Promise<void> {
  // redirect() lève une exception : jamais dans le try.
  let echec: string | null = null
  let sessionPerimee = false
  try {
    await supprimerMesDonnees()
  } catch (erreur) {
    if (!(erreur instanceof ErreurApi)) throw erreur
    // Seul le 401 est « sans objet » : la session n'existe plus, il n'y a rien
    // à supprimer avec elle, et on ne prétend PAS avoir supprimé quoi que ce
    // soit. Tout autre échec (500, 503, 429) a laissé les données en base :
    // effacer le cookie et afficher un succès serait une fausse promesse sur
    // des données personnelles.
    if (erreur.statut === 401) sessionPerimee = true
    else echec = erreur.code
  }

  if (echec) redirect(`/compte/supprimer?erreur=${encodeURIComponent(echec)}`)
  if (sessionPerimee) redirect('/connexion/expiree')

  // Mêmes attributs que `seDeconnecter` : sans `path`, le navigateur garde le cookie.
  const magasin = await cookies()
  magasin.delete({ name: NOM_COOKIE, path: '/' })
  journaliser('donnees_supprimees')
  redirect('/connexion?supprime=1')
}
