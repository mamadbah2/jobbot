import { redirect } from 'next/navigation'

import { listerOffres, moi } from '../api-client'
import { ErreurApi, type Offre } from '../api-contrat'
import { EcranPanne } from '../ecran-panne'
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

/** Au-delà, la page est de toute façon hors limites et l'écran le dira. */
const PAGE_MAX = 100_000

/** Numéro de page borné des DEUX côtés.
 *
 *  En bas : un paramètre absent, non numérique ou négatif retombe sur la
 *  première page plutôt que de casser le rendu.
 *
 *  En haut, et c'est le défaut corrigé : `/offres?page=99999999999999999999`
 *  produisait un décalage que JavaScript écrit en notation scientifique
 *  (« 2e+21 »), que l'API refuse en 422. L'utilisateur lisait alors « Nous
 *  n'arrivons pas à charger cette page » — un message de panne — au lieu de
 *  « cette page n'existe pas », qui est la vérité. */
function pageDemandee(brut: string | undefined): number {
  const nombre = Number(brut)
  if (!Number.isInteger(nombre) || nombre < 1) return 1
  return Math.min(nombre, PAGE_MAX)
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
    return <EcranPanne reessayerHref="/offres" />
  }
  // Session périmée ou absente : on passe par la route qui efface le cookie,
  // sinon il repart à chaque requête pour se faire refuser à chaque fois.
  if (!utilisateur) redirect('/connexion/expiree')

  const { page: pageBrut } = await searchParams
  const pageNum = pageDemandee(pageBrut)
  const decalage = (pageNum - 1) * LIMITE

  let page
  try {
    page = await listerOffres(LIMITE, decalage)
  } catch (erreur) {
    // La session a pu expirer entre `/moi` et cet appel.
    if (erreur instanceof ErreurApi && erreur.statut === 401) redirect('/connexion/expiree')
    return (
      <EcranPanne
        reessayerHref={`/offres?page=${pageNum}`}
        retour={{ href: '/compte', libelle: T.lienCompte }}
      />
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
