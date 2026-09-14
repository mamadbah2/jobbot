// `appeler()` est la fonction la plus critique du client : c'est elle qui pose
// le cookie de session et qui décide d'émettre ou non un `X-Forwarded-For`.
// Elle n'avait aucun test, parce qu'elle importait `next/headers` — un
// sous-chemin que le résolveur ESM de `node --test` ne sait pas résoudre.
// Le contexte de requête est désormais un paramètre à valeur par défaut ; on
// lui injecte ici des doubles, sans dépendance ni composant client.

import { test } from 'node:test'
import assert from 'node:assert/strict'

import { appeler, type ContexteRequete } from '../app/api-client.ts'
import { ErreurApi, NOM_COOKIE } from '../app/api-contrat.ts'

/** Contexte factice : pas de Next, pas de requête, pas de réseau. */
function contexte(
  session: string | undefined,
  entetes: Record<string, string> = {},
): ContexteRequete {
  return {
    cookieSession: async () => session,
    entetesEntrants: async () => new Headers(entetes),
  }
}

/** `fetch` factice : capture la requête au lieu de l'émettre, et rend la
 *  réponse qu'on lui dicte. */
function espionFetch(reponse: Response) {
  const vues: { url: string; entetes: Headers }[] = []
  const envoyer = async (url: string | URL | Request, init?: RequestInit) => {
    vues.push({ url: String(url), entetes: new Headers(init?.headers) })
    return reponse
  }
  return { vues, envoyer: envoyer as unknown as typeof fetch }
}

function reponseOk(): Response {
  return new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } })
}

test('appeler transporte le cookie de session vers l’API', async () => {
  const espion = espionFetch(reponseOk())
  await appeler('/moi', {}, contexte('jeton.abc.def'), espion.envoyer)

  assert.equal(espion.vues.length, 1)
  assert.equal(espion.vues[0]?.entetes.get('cookie'), `${NOM_COOKIE}=jeton.abc.def`)
})

test('appeler n’invente pas de cookie quand la session est absente', async () => {
  const espion = espionFetch(reponseOk())
  await appeler('/moi', {}, contexte(undefined), espion.envoyer)

  assert.equal(espion.vues[0]?.entetes.get('cookie'), null)
})

test("aucun X-Forwarded-For n'est émis tant qu'aucun proxy n'est déclaré", async () => {
  // LE test de la revue finale (constat C1). `WEB_DERRIERE_PROXY` vaut `false`
  // dans l'environnement de test comme en développement : même si le client a
  // forgé l'en-tête, il ne doit PAS être relayé — sinon les plafonds par IP de
  // `core/auth/limites.py` se contournent en faisant tourner la valeur.
  assert.notEqual(
    process.env.WEB_DERRIERE_PROXY,
    'true',
    'ce test suppose WEB_DERRIERE_PROXY non activé',
  )
  const espion = espionFetch(reponseOk())
  await appeler('/moi', {}, contexte('jeton', { 'x-forwarded-for': '1.2.3.4' }), espion.envoyer)

  assert.equal(espion.vues[0]?.entetes.get('x-forwarded-for'), null)
})

test('appeler demande toujours du JSON et vise la bonne URL', async () => {
  const espion = espionFetch(reponseOk())
  await appeler('/offres?limite=20&decalage=0', {}, contexte(undefined), espion.envoyer)

  assert.equal(espion.vues[0]?.entetes.get('accept'), 'application/json')
  assert.ok(espion.vues[0]?.url.endsWith('/offres?limite=20&decalage=0'))
})

test('appeler traduit une réponse en échec en ErreurApi, code compris', async () => {
  const refus = new Response(JSON.stringify({ erreur: 'trop_de_demandes' }), {
    status: 429,
    headers: { 'content-type': 'application/json', 'retry-after': '42' },
  })
  const espion = espionFetch(refus)

  await assert.rejects(
    () => appeler('/auth/code/demande', {}, contexte(undefined), espion.envoyer),
    (erreur: unknown) => {
      assert.ok(erreur instanceof ErreurApi)
      assert.equal(erreur.code, 'trop_de_demandes')
      assert.equal(erreur.statut, 429)
      assert.equal(erreur.reessayerDans, 42)
      return true
    },
  )
})

test('un corps d’erreur non-JSON retombe sur le code par défaut', async () => {
  // Un 502 du reverse proxy rend du HTML, pas du JSON. La page doit afficher
  // un message, jamais planter sur un `json()` qui lève.
  const espion = espionFetch(new Response('<html>Bad Gateway</html>', { status: 502 }))

  await assert.rejects(
    () => appeler('/moi', {}, contexte(undefined), espion.envoyer),
    (erreur: unknown) => {
      assert.ok(erreur instanceof ErreurApi)
      assert.equal(erreur.code, 'defaut')
      assert.equal(erreur.statut, 502)
      return true
    },
  )
})
