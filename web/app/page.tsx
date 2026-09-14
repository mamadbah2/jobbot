import { redirect } from 'next/navigation'

import { moi } from './api-client'
import { EcranPanne } from './ecran-panne'

export default async function PageRacine() {
  let utilisateur
  try {
    utilisateur = await moi()
  } catch {
    // Panne réseau ou serveur pendant l'appel à /moi : `moi()` a déjà
    // résolu un 401 en `null` en interne, donc on n'arrive ici que pour une
    // panne véritable. On ne laisse jamais l'écran d'erreur générique de
    // Next s'afficher (§11 : toujours une sortie).
    return <EcranPanne reessayerHref="/" />
  }
  redirect(utilisateur ? '/offres' : '/connexion')
}
