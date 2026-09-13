// LE SEUL module qui parle à l'API. Aucun `fetch` ailleurs dans web/.
// C'est le pendant de « le LLM n'est appelé que depuis llm/client.py » (§9).

import { cookies, headers } from 'next/headers'

import {
  ErreurApi,
  NOM_COOKIE,
  ipCliente,
  lireCookieSession,
  type CookieSession,
  type PageOffres,
  type Utilisateur,
} from './api-contrat'

const BASE = process.env.API_BASE_URL ?? 'http://api:8080'

async function appeler(chemin: string, init: RequestInit = {}): Promise<Response> {
  const magasin = await cookies()
  const entrants = await headers()
  const entetes = new Headers(init.headers)
  entetes.set('Accept', 'application/json')

  const session = magasin.get(NOM_COOKIE)
  if (session) entetes.set('Cookie', `${NOM_COOKIE}=${session.value}`)

  const ip = ipCliente(entrants)
  if (ip) entetes.set('X-Forwarded-For', ip)

  const reponse = await fetch(`${BASE}${chemin}`, {
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
