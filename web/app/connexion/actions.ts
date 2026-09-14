'use server'

import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

import { COOKIE_ADRESSE, ErreurApi, attributsCookieAdresse } from '../api-contrat'
import { demanderCode } from '../api-client'
import { codeConnu, journaliser } from '../journal'

export async function envoyerCode(formData: FormData): Promise<void> {
  const adresse = String(formData.get('adresse') ?? '').trim()

  if (!adresse) redirect('/connexion?erreur=adresse_invalide')

  // redirect() lève une exception interceptée par Next : jamais dans un try.
  let echec: string | null = null
  try {
    await demanderCode(adresse)
    const magasin = await cookies()
    magasin.set(COOKIE_ADRESSE, adresse, attributsCookieAdresse())
  } catch (erreur) {
    if (erreur instanceof ErreurApi) echec = erreur.code
    else throw erreur
  }

  if (echec) {
    journaliser('adresse_refusee', { code: codeConnu(echec) })
    redirect(`/connexion?erreur=${encodeURIComponent(echec)}`)
  }

  journaliser('code_demande')
  redirect('/connexion/code')
}
