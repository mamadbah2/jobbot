import { journaliser } from '../journal'
import { texteErreur, T } from '../textes'
import { envoyerCode } from './actions'

export default async function PageConnexion({
  searchParams,
}: {
  searchParams: Promise<{ erreur?: string }>
}) {
  const { erreur } = await searchParams
  const message = texteErreur(erreur)

  // Première marche du parcours. Les autres évènements viennent tous de
  // Server Actions, donc de gens qui ont DÉJÀ soumis un formulaire : sans
  // celui-ci, impossible de calculer le taux qui compte — combien ont vu
  // l'écran et sont partis sans rien taper (§11). L'étape seule, aucune
  // donnée personnelle.
  journaliser('vue_connexion')

  return (
    <main>
      <h1>{T.titreAdresse}</h1>
      <p>{T.aideAdresse}</p>
      {message && <p className="erreur">{message}</p>}
      <form action={envoyerCode}>
        <label htmlFor="adresse">{T.champAdresse}</label>
        <input
          id="adresse"
          name="adresse"
          type="email"
          inputMode="email"
          autoComplete="email"
          required
        />
        <button type="submit">{T.boutonAdresse}</button>
      </form>
    </main>
  )
}
