import { redirect } from 'next/navigation'

import { moi } from '../../api-client'
import { EcranPanne } from '../../ecran-panne'
import { T, texteErreur } from '../../textes'
import { supprimerMonCompte } from '../actions'

// Étape de confirmation, sans JavaScript : une action irréversible ne doit pas
// partir d'un tap maladroit sur un écran tactile.
export default async function PageSuppression({
  searchParams,
}: {
  searchParams: Promise<{ erreur?: string }>
}) {
  let utilisateur
  try {
    utilisateur = await moi()
  } catch {
    return (
      <EcranPanne
        reessayerHref="/compte/supprimer"
        retour={{ href: '/compte', libelle: T.lienCompte }}
      />
    )
  }
  if (!utilisateur) redirect('/connexion/expiree')

  const { erreur } = await searchParams
  const message = texteErreur(erreur)

  return (
    <main>
      <nav>
        <a href="/compte">{T.lienCompte}</a>
      </nav>
      <h1>{T.titreSuppression}</h1>
      <p>{T.aideSuppression}</p>
      {message && <p className="erreur">{message}</p>}
      <form action={supprimerMonCompte}>
        <button type="submit">{T.boutonSupprimer}</button>
      </form>
      <p className="issue-secours">
        <a href="/compte">{T.annuler}</a>
      </p>
    </main>
  )
}
