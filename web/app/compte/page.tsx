import { redirect } from 'next/navigation'

import { moi } from '../api-client'
import { T } from '../textes'
import { seDeconnecter } from './actions'

export default async function PageCompte() {
  const utilisateur = await moi()
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
      <form action={seDeconnecter}>
        <button type="submit">{T.boutonDeconnexion}</button>
      </form>
    </main>
  )
}
