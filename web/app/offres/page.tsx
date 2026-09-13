import { redirect } from 'next/navigation'

import { listerOffres, moi } from '../api-client'
import { ErreurApi, type Offre } from '../api-contrat'
import { T } from '../textes'

const LIMITE = 20

function commentPostuler(methode: string): string {
  if (methode === 'email') return T.parEmail
  if (methode === 'form') return T.parFormulaire
  return T.parSiteExterne
}

/** N'accepte qu'un lien http(s) : les offres viennent de pages tierces que
 *  nous ne maîtrisons pas (`src/ingest/store.py` ne contrôle que la longueur,
 *  aucun schéma). Une URL absente ou mal formée est traitée comme invalide,
 *  jamais comme une exception qui ferait planter la page. */
function urlSure(url: string): string | null {
  try {
    const analysee = new URL(url)
    return analysee.protocol === 'http:' || analysee.protocol === 'https:' ? url : null
  } catch {
    return null
  }
}

/** Date courte et lisible (« 12 septembre 2026 »), jamais un horodatage ISO.
 *  `null` — offre sans date, ou date qui ne parse pas — n'affiche rien : pas
 *  de « date inconnue » qui prendrait de la place pour rien. */
function dateLisible(publieeLe: string | null): string | null {
  if (!publieeLe) return null
  const date = new Date(publieeLe)
  if (Number.isNaN(date.getTime())) return null
  return new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' }).format(
    date,
  )
}

/** Numéro de page borné à 1 minimum : un paramètre absent, non numérique ou
 *  négatif retombe sur la première page plutôt que de casser le rendu. */
function pageDemandee(brut: string | undefined): number {
  const nombre = Number(brut)
  return Number.isInteger(nombre) && nombre >= 1 ? nombre : 1
}

function LigneOffre({ offre }: { offre: Offre }) {
  const details = [offre.entreprise, offre.lieu, offre.type_contrat].filter(Boolean).join(' · ')
  const date = dateLisible(offre.publiee_le)
  const lien = urlSure(offre.url)
  return (
    <li className="offre">
      <h2>{offre.titre}</h2>
      {details && <p className="meta">{details}</p>}
      {date && <p className="meta">{date}</p>}
      <p className="meta">{commentPostuler(offre.methode_candidature)}</p>
      {lien ? (
        <a href={lien} rel="noopener noreferrer" target="_blank">
          {T.voirOffre}
        </a>
      ) : (
        <p className="meta">{T.lienIndisponible}</p>
      )}
    </li>
  )
}

export default async function PageOffres({
  searchParams,
}: {
  searchParams: Promise<{ page?: string }>
}) {
  let utilisateur
  try {
    utilisateur = await moi()
  } catch {
    // Panne réseau ou serveur : message court, action possible, jamais
    // l'écran d'erreur générique de Next (§11). `moi()` a déjà résolu un 401
    // en `null` en interne, donc on n'arrive ici que pour une panne réelle.
    return (
      <main>
        <p>{T.erreurTemporaire}</p>
        <a href="/offres">{T.reessayer}</a>
      </main>
    )
  }
  if (!utilisateur) redirect('/connexion')

  const { page: pageBrut } = await searchParams
  const pageNum = pageDemandee(pageBrut)
  const decalage = (pageNum - 1) * LIMITE

  let page
  try {
    page = await listerOffres(LIMITE, decalage)
  } catch (erreur) {
    if (erreur instanceof ErreurApi && erreur.statut === 401) redirect('/connexion')
    return (
      <main>
        <nav>
          <a href="/compte">{T.lienCompte}</a>
        </nav>
        <p>{T.erreurTemporaire}</p>
        <a href={`/offres?page=${pageNum}`}>{T.reessayer}</a>
      </main>
    )
  }

  // Page demandée au-delà du total réel (ex. lien gardé en favori après que
  // l'offre a expiré, ou saisie manuelle) : liste vide mais explicable,
  // jamais une liste vide silencieuse.
  const pageHorsLimites = pageNum > 1 && page.offres.length === 0 && page.total > 0
  const dernierePage = Math.max(1, Math.ceil(page.total / LIMITE))
  const precedenteExiste = pageNum > 1
  const suivanteExiste = !pageHorsLimites && pageNum < dernierePage

  return (
    <main>
      <nav>
        <a href="/compte">{T.lienCompte}</a>
      </nav>
      <h1>{T.titreOffres}</h1>
      {page.total === 0 ? (
        <p>{T.aucuneOffre}</p>
      ) : pageHorsLimites ? (
        <>
          <p>{T.pageInexistante}</p>
          <a href="/offres">{T.revenirPremierePage}</a>
        </>
      ) : (
        <>
          <ul style={{ listStyle: 'none', padding: 0 }}>
            {page.offres.map((offre) => (
              <LigneOffre key={offre.id} offre={offre} />
            ))}
          </ul>
          {(precedenteExiste || suivanteExiste) && (
            <nav>
              {precedenteExiste && <a href={`/offres?page=${pageNum - 1}`}>{T.pagePrecedente}</a>}
              {precedenteExiste && suivanteExiste && ' · '}
              {suivanteExiste && <a href={`/offres?page=${pageNum + 1}`}>{T.pageSuivante}</a>}
            </nav>
          )}
        </>
      )}
    </main>
  )
}
