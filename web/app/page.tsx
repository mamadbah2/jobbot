import { redirect } from 'next/navigation'

import { moi } from './api-client'
import { T } from './textes'

export default async function PageRacine() {
  let utilisateur
  try {
    utilisateur = await moi()
  } catch {
    // Panne réseau ou serveur pendant l'appel à /moi : `moi()` a déjà
    // résolu un 401 en `null` en interne, donc on n'arrive ici que pour une
    // panne véritable. On ne laisse jamais l'écran d'erreur générique de
    // Next s'afficher (§11 : toujours une sortie).
    return (
      <main>
        <p>{T.erreurTemporaire}</p>
        <a href="/">{T.reessayer}</a>
      </main>
    )
  }
  redirect(utilisateur ? '/offres' : '/connexion')
}
