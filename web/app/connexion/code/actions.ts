'use server'

import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

import { COOKIE_ADRESSE, ErreurApi, attributsCookieSession } from '../../api-contrat'
import { verifierCode } from '../../api-client'
import { codeConnu, journaliser } from '../../journal'

export async function validerCode(formData: FormData): Promise<void> {
  const magasin = await cookies()
  const adresse = magasin.get(COOKIE_ADRESSE)?.value

  // Le cookie a expiré (15 min) ou l'utilisateur est arrivé là directement.
  if (!adresse) redirect('/connexion?erreur=code_expire')

  const code = String(formData.get('code') ?? '').trim()
  const nom = String(formData.get('nom') ?? '').trim()

  let echec: string | null = null
  try {
    const { session } = await verifierCode(adresse, code, nom || undefined)
    if (session) {
      magasin.set(session.nom, session.valeur, attributsCookieSession(session.maxAge))
    }
    magasin.delete(COOKIE_ADRESSE)
  } catch (erreur) {
    if (erreur instanceof ErreurApi) echec = erreur.code
    else throw erreur
  }

  // Ce n'est pas une erreur mais un aiguillage : le compte est nouveau, donc
  // l'API réclame un nom. Elle a redéposé le code, il reste valide.
  if (echec === 'inscription_incomplete' || echec === 'nom_invalide') {
    journaliser('nom_demande')
    redirect(`/connexion/code?nom=requis&erreur=${encodeURIComponent(echec)}`)
  }

  if (echec) {
    journaliser('code_refuse', { code: codeConnu(echec) })
    redirect(`/connexion/code?erreur=${encodeURIComponent(echec)}`)
  }

  journaliser('connexion_reussie')
  redirect('/offres')
}
