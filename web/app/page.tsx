import { redirect } from 'next/navigation'

import { moi } from './api-client'

export default async function PageRacine() {
  const utilisateur = await moi()
  redirect(utilisateur ? '/offres' : '/connexion')
}
