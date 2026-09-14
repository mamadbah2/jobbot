import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

import { COOKIE_ADRESSE } from '../../api-contrat'
import { journaliser } from '../../journal'
import { texteErreur, T } from '../../textes'
import { validerCode } from './actions'

export default async function PageCode({
  searchParams,
}: {
  searchParams: Promise<{ erreur?: string; nom?: string }>
}) {
  const magasin = await cookies()
  if (!magasin.get(COOKIE_ADRESSE)) redirect('/connexion')

  const { erreur, nom } = await searchParams
  const message = texteErreur(erreur)
  const nomRequis = nom === 'requis'

  // Après le `redirect` ci-dessus, donc seulement quand l'écran s'affiche
  // vraiment. C'est ici qu'on perd les gens qui n'ont pas reçu le code et
  // qui referment l'onglet : sans cette vue, cet abandon est invisible.
  journaliser('vue_code')

  return (
    <main>
      <h1>{T.titreCode}</h1>
      <p>{T.aideCode}</p>
      {message && <p className="erreur">{message}</p>}
      <form action={validerCode}>
        <label htmlFor="code">{T.champCode}</label>
        <input
          id="code"
          name="code"
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          required
        />
        {nomRequis && (
          <>
            <p>{T.aideNom}</p>
            <label htmlFor="nom">{T.champNom}</label>
            <input id="nom" name="nom" type="text" autoComplete="name" required />
          </>
        )}
        <button type="submit">{T.boutonCode}</button>
      </form>
      <p className="issue-secours">
        <a href="/connexion">{T.retourConnexion}</a>
      </p>
    </main>
  )
}
