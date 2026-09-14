import { redirect } from 'next/navigation'

import { moi } from '../api-client'
import { etatLisible, T } from '../textes'
import { seDeconnecter } from './actions'

export default async function PageCompte() {
  let utilisateur
  try {
    utilisateur = await moi()
  } catch {
    // Panne réseau ou serveur : message court, action possible, jamais
    // l'écran d'erreur générique de Next (§11).
    return (
      <main>
        <nav>
          <a href="/offres">{T.lienOffres}</a>
        </nav>
        <p>{T.erreurTemporaire}</p>
        <a href="/compte">{T.reessayer}</a>
      </main>
    )
  }
  if (!utilisateur) redirect('/connexion')

  return (
    <main>
      <nav>
        <a href="/offres">{T.lienOffres}</a>
      </nav>
      <h1>{T.titreCompte}</h1>
      <p>
        {utilisateur.nom_complet ?? ''}
        <br />
        {utilisateur.email}
      </p>
      {/* L'état, que la spec §5 réclame et que le plan avait perdu en route.
          `etatLisible` en fait une phrase : « active » est un identifiant de
          base de données, pas une information pour l'utilisateur. */}
      <p className="meta">{etatLisible(utilisateur.etat)}</p>
      <form action={seDeconnecter}>
        <button type="submit">{T.boutonDeconnexion}</button>
      </form>
    </main>
  )
}
