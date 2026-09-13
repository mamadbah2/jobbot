// Mesure le poids réellement transféré d'une page, compression comprise.
//
// Sans dépendance : ajouter Playwright pour ça coûterait plus que ça ne
// rapporte (CLAUDE.md §3).
//
// LIMITE ASSUMÉE : ne voit pas un fragment chargé dynamiquement. Avec zéro
// composant client et aucun import dynamique, il n'y en a pas. Si cela change,
// cette mesure devient fausse SANS PRÉVENIR — d'où la double vérification en
// vrai navigateur à la validation de la phase.

const BASE = process.env.URL_BASE ?? 'http://127.0.0.1:3000'
const CHEMIN = process.argv[2] ?? '/connexion'
const PLAFOND = Number(process.env.PLAFOND_OCTETS ?? 200 * 1024)

const ENTETES = { 'Accept-Encoding': 'gzip, deflate, br' }

async function poids(url) {
  const reponse = await fetch(url, { headers: ENTETES, redirect: 'follow' })
  if (!reponse.ok) throw new Error(`${url} → HTTP ${reponse.status}`)
  const corps = await reponse.arrayBuffer()
  return { octets: corps.byteLength, texte: reponse.headers.get('content-type') ?? '' }
}

const html = await fetch(`${BASE}${CHEMIN}`, { headers: ENTETES, redirect: 'follow' })
if (!html.ok) throw new Error(`${CHEMIN} → HTTP ${html.status}`)
const source = await html.text()
const octetsHtml = Buffer.byteLength(source)

const refs = new Set()
for (const m of source.matchAll(/<script[^>]+src="([^"]+)"/g)) refs.add(m[1])
for (const m of source.matchAll(/<link[^>]+href="([^"]+\.(?:css|js|woff2?))"/g)) refs.add(m[1])

let total = octetsHtml
const lignes = [['(document HTML)', octetsHtml]]
for (const ref of refs) {
  const url = ref.startsWith('http') ? ref : `${BASE}${ref}`
  const { octets } = await poids(url)
  total += octets
  lignes.push([ref, octets])
}

lignes.sort((a, b) => b[1] - a[1])
for (const [nom, octets] of lignes) {
  console.log(`${String(Math.round(octets / 1024)).padStart(5)} Ko  ${nom}`)
}
console.log('—'.repeat(50))
console.log(`${String(Math.round(total / 1024)).padStart(5)} Ko  TOTAL pour ${CHEMIN}`)
console.log(`${String(Math.round(PLAFOND / 1024)).padStart(5)} Ko  plafond`)

if (total > PLAFOND) {
  console.error(`\nÉCHEC : ${Math.round(total / 1024)} Ko dépassent le plafond.`)
  process.exit(1)
}
console.log('\nOK.')
