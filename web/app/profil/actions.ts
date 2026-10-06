'use server'

import { redirect } from 'next/navigation'

import { ErreurApi } from '../api-contrat'
import { corrigerProfil, deposerCv } from '../api-client'
import { codeConnu, journaliser } from '../journal'

export async function envoyerCv(formData: FormData): Promise<void> {
  const fichier = formData.get('fichier')
  if (!(fichier instanceof File) || fichier.size === 0) {
    redirect('/profil?erreur=cv_type_refuse')
  }

  // redirect() lève une exception interceptée par Next : jamais dans un try,
  // sinon le catch l'avalerait et la page n'irait nulle part.
  let echec: string | null = null
  try {
    await deposerCv(fichier)
  } catch (erreur) {
    if (erreur instanceof ErreurApi) echec = erreur.code
    else throw erreur
  }

  if (echec) {
    // `codeConnu` : seul un code de notre liste fermée entre dans les journaux.
    journaliser('cv_refuse', { code: codeConnu(echec) })
    redirect(`/profil?erreur=${encodeURIComponent(echec)}`)
  }
  journaliser('cv_depose')
  redirect('/profil')
}

export async function enregistrerProfil(formData: FormData): Promise<void> {
  const liste = (cle: string): string[] =>
    String(formData.get(cle) ?? '')
      .split(',')
      .map((v) => v.trim())
      .filter(Boolean)

  const donnees = {
    nom_complet: String(formData.get('nom_complet') ?? '').trim() || null,
    titre: String(formData.get('titre') ?? '').trim() || null,
    competences: liste('competences'),
    langues: liste('langues'),
    secteurs_vises: formData.getAll('secteurs').map(String),
    mobilite: String(formData.get('region') ?? '').trim() || null,
    type_contrat: String(formData.get('contrat') ?? '').trim() || null,
  }

  let echec: string | null = null
  try {
    await corrigerProfil(donnees)
  } catch (erreur) {
    if (erreur instanceof ErreurApi) echec = erreur.code
    else throw erreur
  }

  if (echec) redirect(`/profil?erreur=${encodeURIComponent(echec)}`)
  journaliser('profil_valide')
  redirect('/offres')
}
