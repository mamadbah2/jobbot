'use server'

import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

import {
  COOKIE_BROUILLON,
  ErreurApi,
  attributsCookieBrouillon,
  effacementCookieBrouillon,
  listeTropLongue,
  serialiserBrouillon,
  type BrouillonProfil,
} from '../api-contrat'
import { corrigerProfil, deposerCv } from '../api-client'
import { codeConnu, journaliser } from '../journal'

/** Conserve la saisie le temps d'un aller-retour d'erreur, ou l'oublie quand
 *  elle est enregistrée. Sans JavaScript, le `redirect` qui porte le message
 *  d'erreur recharge la page depuis la base : sans ce cookie, tout ce que
 *  l'utilisateur vient de taper disparaît avec lui. */
async function conserver(donnees: BrouillonProfil): Promise<void> {
  const valeur = serialiserBrouillon(donnees)
  const magasin = await cookies()
  // Trop gros pour un cookie : on l'oublie plutôt que d'en poser un que le
  // navigateur jettera sans rien dire.
  if (valeur) magasin.set(COOKIE_BROUILLON, valeur, attributsCookieBrouillon())
  else magasin.delete(effacementCookieBrouillon())
}

async function oublier(): Promise<void> {
  const magasin = await cookies()
  // Avec le chemin : un navigateur n'efface un cookie que si le chemin
  // correspond, et celui-ci est posé sur `/profil`, pas sur `/`.
  magasin.delete(effacementCookieBrouillon())
}

export async function envoyerCv(formData: FormData): Promise<void> {
  const fichier = formData.get('fichier')
  if (!(fichier instanceof File) || fichier.size === 0) {
    redirect('/profil?erreur=cv_type_refuse')
  }

  // Un nouveau CV remplace le profil : un brouillon de l'ancien n'a plus de
  // sens et se rappliquerait sur l'écran de validation du nouveau.
  await oublier()

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

  const donnees: BrouillonProfil = {
    nom_complet: String(formData.get('nom_complet') ?? '').trim() || null,
    titre: String(formData.get('titre') ?? '').trim() || null,
    competences: liste('competences'),
    langues: liste('langues'),
    secteurs_vises: formData.getAll('secteurs').map(String),
    mobilite: String(formData.get('region') ?? '').trim() || null,
    type_contrat: String(formData.get('contrat') ?? '').trim() || null,
  }

  // Les mêmes plafonds que `CorrectionProfil`, vérifiés AVANT l'appel : l'API
  // les refuse avec un 422 de pydantic, sans code d'erreur exploitable, et
  // l'écran ne saurait dire que « une erreur est survenue » — devant quoi
  // l'utilisateur n'a aucune action possible (revue finale, I-2).
  const trop = listeTropLongue(donnees)
  if (trop) {
    await conserver(donnees)
    journaliser('profil_trop_long')
    redirect(`/profil?trop=${trop.champ}&saisi=${trop.saisi}`)
  }

  let echec: string | null = null
  try {
    await corrigerProfil(donnees)
  } catch (erreur) {
    if (erreur instanceof ErreurApi) echec = erreur.code
    else throw erreur
  }

  if (echec) {
    // La saisie survit aussi aux refus de l'API : c'est le même aller-retour.
    await conserver(donnees)
    redirect(`/profil?erreur=${encodeURIComponent(echec)}`)
  }
  await oublier()
  journaliser('profil_valide')
  redirect('/offres')
}
