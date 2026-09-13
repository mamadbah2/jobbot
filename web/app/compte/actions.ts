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
  const magasin = await cookies()
  magasin.delete(NOM_COOKIE)

  journaliser('deconnexion')
  redirect('/connexion')
}
