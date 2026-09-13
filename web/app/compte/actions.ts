'use server'

import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

import { ErreurApi, NOM_COOKIE } from '../api-contrat'
import { deconnecter } from '../api-client'
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
