// Mesure le poids réellement transféré d'une page, compression comprise.
//
// Sans dépendance : ajouter Playwright pour ça coûterait plus que ça ne
// rapporte (CLAUDE.md §3).
//
// LIMITE ASSUMÉE : ne voit pas un fragment chargé dynamiquement. Avec zéro
// composant client et aucun import dynamique, il n'y en a pas. Si cela change,
// cette mesure devient fausse SANS PRÉVENIR — d'où la double vérification en
// vrai navigateur à la validation de la phase.
//
// DEUX DÉFAUTS CORRIGÉS LE 2026-09-13, À NE PAS RECOMMETTRE DANS SIX MOIS :
//
// Défaut A — fetch() décompresse en silence. La première version utilisait
// fetch()/arrayBuffer(), qui rend le corps DÉCOMPRESSÉ — exactement comme le
// fetch() d'un navigateur : Response.arrayBuffer() ne redonne jamais les
// octets bruts compressés, il n'y a aucun moyen de les lire via l'API Fetch.
// Le total mesuré était donc 3 à 4x trop gros. Remède : node:http, qui ne
// décompresse rien — on compte les octets tels qu'ils arrivent du socket,
// ce qui EST le poids transféré.
//
// Défaut B — un <script nomodule> n'est jamais téléchargé par un navigateur
// qui comprend les modules ES (tout Android Chrome depuis 2018, notre cible).
// Le compter dans le total fausse la mesure de plusieurs dizaines de Ko (le
// polyfill hérité que Next sert aux vieux navigateurs). On classe donc les
// scripts nomodule à part et on les exclut du total qui fait foi — mais on
// les affiche quand même, pour que personne ne soupçonne plus tard qu'on a
// triché sur le chiffre en les cachant.

import { get as requeteHttp } from 'node:http'
import { gunzipSync, brotliDecompressSync, inflateSync } from 'node:zlib'

const BASE = process.env.URL_BASE ?? 'http://127.0.0.1:3000'
const CHEMIN = process.argv[2] ?? '/connexion'
const PLAFOND = Number(process.env.PLAFOND_OCTETS ?? 200 * 1024)

const ENTETES = { 'Accept-Encoding': 'gzip, deflate, br' }

/** Compte les octets RÉELLEMENT transférés : `node:http` ne décompresse pas,
 *  contrairement à `fetch()`, dont l'`arrayBuffer()` rend le contenu détendu. */
function telecharger(url, sauts = 0) {
  return new Promise((resolve, reject) => {
    requeteHttp(url, { headers: ENTETES }, (reponse) => {
      const { statusCode, headers } = reponse
      // Suit les redirections (comme le faisait fetch avec redirect: 'follow').
      if (statusCode >= 300 && statusCode < 400 && headers.location && sauts < 5) {
        reponse.resume()
        resolve(telecharger(new URL(headers.location, url).toString(), sauts + 1))
        return
      }
      if (statusCode !== 200) {
        reponse.resume()
        reject(new Error(`${url} → HTTP ${statusCode}`))
        return
      }
      let octets = 0
      const morceaux = []
      reponse.on('data', (m) => {
        octets += m.length
        morceaux.push(m)
      })
      reponse.on('end', () =>
        resolve({ octets, morceaux, encodage: headers['content-encoding'] ?? 'identity' }),
      )
    }).on('error', reject)
  })
}

// Ne sert qu'à relire le HTML pour y repérer les références aux fragments —
// le total, lui, se base uniquement sur `octets` (les octets sur le fil).
function detendre({ morceaux, encodage }) {
  const brut = Buffer.concat(morceaux)
  if (encodage === 'gzip') return gunzipSync(brut).toString('utf8')
  if (encodage === 'br') return brotliDecompressSync(brut).toString('utf8')
  if (encodage === 'deflate') return inflateSync(brut).toString('utf8')
  return brut.toString('utf8')
}

const page = await telecharger(`${BASE}${CHEMIN}`)
const source = detendre(page)
const octetsHtml = page.octets

// Balise <script> entière (pas seulement son src) pour pouvoir vérifier la
// présence de l'attribut nomodule. Next l'écrit `noModule=""` ; on compare
// en minuscules pour ne pas dépendre de la casse.
const scripts = []
for (const m of source.matchAll(/<script\b[^>]*>/g)) {
  const balise = m[0]
  const src = balise.match(/\ssrc="([^"]+)"/)?.[1]
  if (!src) continue
  scripts.push({ src, herite: /\bnomodule\b/i.test(balise) })
}

const feuilles = [...source.matchAll(/<link[^>]+href="([^"]+\.(?:css|woff2?))"/g)].map((m) => m[1])

async function poidsTransfere(ref) {
  const url = ref.startsWith('http') ? ref : `${BASE}${ref}`
  const { octets } = await telecharger(url)
  return octets
}

const moderne = [['(document HTML)', octetsHtml]]
const heritees = []
for (const { src, herite } of scripts) {
  const octets = await poidsTransfere(src)
  ;(herite ? heritees : moderne).push([src, octets])
}
for (const href of feuilles) {
  moderne.push([href, await poidsTransfere(href)])
}

function afficher(titre, lignes) {
  console.log(titre)
  for (const [nom, octets] of [...lignes].sort((a, b) => b[1] - a[1])) {
    console.log(`${String(Math.round(octets / 1024)).padStart(5)} Ko  ${nom}`)
  }
  return lignes.reduce((s, [, o]) => s + o, 0)
}

const totalModerne = afficher('— Transféré vers un navigateur moderne (ce total fait foi) —', moderne)
console.log('—'.repeat(50))
console.log(`${String(Math.round(totalModerne / 1024)).padStart(5)} Ko  TOTAL pour ${CHEMIN}`)
console.log(`${String(Math.round(PLAFOND / 1024)).padStart(5)} Ko  plafond`)

if (heritees.length > 0) {
  console.log()
  const totalHerite = afficher(
    '— Hérité, jamais transféré vers notre cible (attribut nomodule : ignoré par tout navigateur ES-modules, donc par tout Android Chrome depuis 2018) —',
    heritees,
  )
  console.log(`${String(Math.round(totalHerite / 1024)).padStart(5)} Ko  hors total, non transféré`)
}

if (totalModerne > PLAFOND) {
  console.error(`\nÉCHEC : ${Math.round(totalModerne / 1024)} Ko dépassent le plafond.`)
  process.exit(1)
}
console.log('\nOK.')
