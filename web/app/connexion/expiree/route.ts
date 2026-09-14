// Efface le cookie de session périmé, puis renvoie vers /connexion.
//
// Pourquoi une route et non un `cookies().delete()` dans la page : Next
// interdit de modifier les cookies pendant le rendu d'un Server Component.
// Seuls une Server Action et un Route Handler en ont le droit. Sans ce
// détour, un cookie invalide restait dans le navigateur et repartait à chaque
// requête, pour se faire refuser à chaque fois.
//
// `path` explicite : un navigateur n'efface un cookie que si les attributs
// correspondent à ceux posés (`attributsCookieSession`, `path: '/'`).

import { cookies } from 'next/headers'

import { NOM_COOKIE } from '../../api-contrat.ts'

export const dynamic = 'force-dynamic'

export async function GET(): Promise<Response> {
  const magasin = await cookies()
  magasin.delete({ name: NOM_COOKIE, path: '/' })
  // `Location` RELATIF, et surtout pas `Response.redirect()`, qui exige une
  // URL absolue : celle-ci se construirait à partir de `request.url`, que le
  // serveur autonome dérive de HOSTNAME — posé à 0.0.0.0 dans le Dockerfile.
  // Le navigateur recevrait alors « http://0.0.0.0:3000/connexion » et
  // n'irait nulle part. Un chemin relatif se résout toujours contre l'URL
  // réellement demandée, quel que soit le proxy devant.
  // 303 : la suite est un GET, quelle que soit la méthode d'origine.
  return new Response(null, { status: 303, headers: { location: '/connexion' } })
}
