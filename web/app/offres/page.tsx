import { redirect } from 'next/navigation'

import { listerOffres, moi } from '../api-client'
import type { Offre } from '../api-contrat'
import { T } from '../textes'

function commentPostuler(methode: string): string {
  if (methode === 'email') return T.parEmail
  if (methode === 'form') return T.parFormulaire
  return T.parSiteExterne
}

function LigneOffre({ offre }: { offre: Offre }) {
  const details = [offre.entreprise, offre.lieu, offre.type_contrat].filter(Boolean).join(' · ')
  return (
    <li className="offre">
      <h2>{offre.titre}</h2>
      {details && <p className="meta">{details}</p>}
      <p className="meta">{commentPostuler(offre.methode_candidature)}</p>
      <a href={offre.url} rel="noopener noreferrer" target="_blank">
        {T.voirOffre}
      </a>
    </li>
  )
}

export default async function PageOffres() {
  const utilisateur = await moi()
  if (!utilisateur) redirect('/connexion')

  const page = await listerOffres(20, 0)

  return (
    <main>
      <nav>
        <a href="/compte">{T.lienCompte}</a>
      </nav>
      <h1>{T.titreOffres}</h1>
      {page.offres.length === 0 ? (
        <p>{T.aucuneOffre}</p>
      ) : (
        <ul style={{ listStyle: 'none', padding: 0 }}>
          {page.offres.map((offre) => (
            <LigneOffre key={offre.id} offre={offre} />
          ))}
        </ul>
      )}
    </main>
  )
}
