// LE SEUL module qui parle à l'API. Aucun `fetch` ailleurs dans web/.
// C'est le pendant de « le LLM n'est appelé que depuis llm/client.py » (§9).
//
// AUCUN import statique de `next/headers` ici, et c'est délibéré : le
// résolveur ESM de `node --test` ne sait pas résoudre ce sous-chemin, et un
// import statique rendrait ce module inchargeable par les tests. La fonction
// la plus critique du client — celle qui pose le cookie de session et décide
// d'émettre ou non un `X-Forwarded-For` — resterait alors la seule sans test.
// Le contexte de requête est donc lu paresseusement, derrière un paramètre à
// valeur par défaut que les tests remplacent par des doubles.

import {
  ErreurApi,
  NOM_COOKIE,
  ipCliente,
  lireCookieSession,
  type CookieSession,
  type PageOffres,
  type Utilisateur,
} from './api-contrat.ts'

const BASE = process.env.API_BASE_URL ?? 'http://api:8080'

/** Les deux seuls accès au contexte de requête dont `appeler` a besoin. */
export type ContexteRequete = {
  /** Valeur du cookie de session, ou `undefined` quand il n'y en a pas. */
  cookieSession: () => Promise<string | undefined>
  /** En-têtes entrants, dont on ne tire que l'IP cliente. */
  entetesEntrants: () => Promise<Headers>
}

/** Le contexte réel : celui de Next, chargé à l'appel et non à l'import. */
const CONTEXTE_NEXT: ContexteRequete = {
  cookieSession: async () => {
    const { cookies } = await import('next/headers')
    return (await cookies()).get(NOM_COOKIE)?.value
  },
  entetesEntrants: async () => {
    const { headers } = await import('next/headers')
    return await headers()
  },
}

export async function appeler(
  chemin: string,
  init: RequestInit = {},
  contexte: ContexteRequete = CONTEXTE_NEXT,
  envoyer: typeof fetch = fetch,
): Promise<Response> {
  const entetes = new Headers(init.headers)
  entetes.set('Accept', 'application/json')

  const session = await contexte.cookieSession()
  if (session) entetes.set('Cookie', `${NOM_COOKIE}=${session}`)

  // `ipCliente` rend `null` tant qu'aucun reverse proxy n'est déclaré
  // (WEB_DERRIERE_PROXY) : on n'émet alors AUCUN en-tête, plutôt que de
  // relayer une valeur que le client a pu écrire lui-même.
  const ip = ipCliente(await contexte.entetesEntrants())
  if (ip) entetes.set('X-Forwarded-For', ip)

  const reponse = await envoyer(`${BASE}${chemin}`, {
    ...init,
    headers: entetes,
    cache: 'no-store',
  })

  if (!reponse.ok) {
    let code = 'defaut'
    try {
      code = ((await reponse.json()) as { erreur?: string }).erreur ?? 'defaut'
    } catch {
      // Corps non-JSON : on garde le code par défaut.
    }
    const retry = reponse.headers.get('retry-after')
    throw new ErreurApi(code, reponse.status, retry ? Number(retry) : undefined)
  }
  return reponse
}

function corpsJson(donnees: unknown): RequestInit {
  return {
    method: 'POST',
    body: JSON.stringify(donnees),
    headers: { 'Content-Type': 'application/json' },
  }
}

export async function demanderCode(adresse: string): Promise<void> {
  await appeler('/auth/code/demande', corpsJson({ email: adresse }))
}

export async function verifierCode(
  adresse: string,
  code: string,
  nomComplet?: string,
): Promise<{ utilisateur: Utilisateur; session: CookieSession | null }> {
  const reponse = await appeler(
    '/auth/code/verifie',
    corpsJson({ email: adresse, code, nom_complet: nomComplet ?? null }),
  )
  return {
    utilisateur: (await reponse.json()) as Utilisateur,
    session: lireCookieSession(reponse.headers),
  }
}

export async function moi(): Promise<Utilisateur | null> {
  try {
    return (await (await appeler('/moi')).json()) as Utilisateur
  } catch (erreur) {
    if (erreur instanceof ErreurApi && erreur.statut === 401) return null
    throw erreur
  }
}

export async function listerOffres(limite = 20, decalage = 0): Promise<PageOffres> {
  const reponse = await appeler(`/offres?limite=${limite}&decalage=${decalage}`)
  return (await reponse.json()) as PageOffres
}

export async function deconnecter(): Promise<void> {
  await appeler('/auth/deconnexion', { method: 'POST' })
}
