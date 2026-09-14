// 404. Sans ce fichier, Next sert son écran d'usine : « This page could not be
// found », en anglais, sans lien de sortie et avec un texte hors de
// `textes.ts` — trois règles du §11 violées d'un coup.
//
// PAS de `'use client'`, et ce n'est pas un oubli : contrairement à
// `error.tsx`, `not-found.tsx` est un Server Component ordinaire. Rien ici ne
// s'exécute chez l'utilisateur.

import { T } from './textes'

export default function Introuvable() {
  return (
    <main>
      <h1>{T.titreIntrouvable}</h1>
      <p>{T.aideIntrouvable}</p>
      <p>
        <a href="/">{T.retourAccueil}</a>
      </p>
    </main>
  )
}
