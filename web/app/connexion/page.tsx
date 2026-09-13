import { texteErreur, T } from '../textes'
import { envoyerCode } from './actions'

export default async function PageConnexion({
  searchParams,
}: {
  searchParams: Promise<{ erreur?: string }>
}) {
  const { erreur } = await searchParams
  const message = texteErreur(erreur)

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
