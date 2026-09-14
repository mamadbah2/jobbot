// Sonde de vivacité du process `web` — l'équivalent du /health de l'API, qui
// est servi par un autre process sur un autre port. Le chemin diffère
// volontairement (`/sante` et non `/health`) pour qu'on sache toujours, en
// lisant une commande, lequel des deux répond.
//
// Pourquoi une route dédiée plutôt que de sonder `/connexion` : cet écran
// émet un évènement de parcours à chaque affichage (`web/app/journal.ts`,
// §11). Un healthcheck toutes les 15 s y injecterait des milliers de fausses
// vues par jour et rendrait le taux d'abandon inexploitable — la mesure même
// qu'on cherche à obtenir.
//
// Route Handler, donc code serveur : aucun `'use client'` ici.

export const dynamic = 'force-dynamic'

export function GET(): Response {
  return new Response('ok', { headers: { 'content-type': 'text/plain' } })
}
