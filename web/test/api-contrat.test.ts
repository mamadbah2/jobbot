import { test } from 'node:test'
import assert from 'node:assert/strict'

import { ipCliente, lireCookieSession, attributsCookieSession } from '../app/api-contrat.ts'
import { texteErreur, ERREURS } from '../app/textes.ts'

test("ipCliente ne garde que la première IP de la chaîne", () => {
  const entetes = new Headers({ 'x-forwarded-for': '41.82.1.9, 172.18.0.4, 10.0.0.2' })
  assert.equal(ipCliente(entetes), '41.82.1.9')
})

test("ipCliente rend null quand l'en-tête est absent", () => {
  assert.equal(ipCliente(new Headers()), null)
})

test('lireCookieSession extrait la valeur et le max-age', () => {
  const entetes = new Headers()
  entetes.append(
    'set-cookie',
    'jobbot_session=abc.def.ghi; Max-Age=2592000; Path=/; HttpOnly; SameSite=lax',
  )
  const session = lireCookieSession(entetes)
  assert.equal(session?.valeur, 'abc.def.ghi')
  assert.equal(session?.maxAge, 2592000)
})

test('lireCookieSession ignore un cookie qui ne porte pas le bon nom', () => {
  const entetes = new Headers()
  entetes.append('set-cookie', 'autre=valeur; Path=/')
  assert.equal(lireCookieSession(entetes), null)
})

test('le cookie de session reste httpOnly et SameSite=lax', () => {
  const a = attributsCookieSession(2592000)
  assert.equal(a.httpOnly, true)
  assert.equal(a.sameSite, 'lax')
  assert.equal(a.path, '/')
  assert.equal(a.maxAge, 2592000)
})

test('chaque code d’erreur de l’API a une phrase', () => {
  for (const code of [
    'adresse_invalide',
    'trop_de_demandes',
    'plafond_global_atteint',
    'envoi_impossible',
    'code_invalide',
    'code_expire',
    'inscription_incomplete',
    'nom_invalide',
    'jeton_invalide',
  ]) {
    assert.ok(ERREURS[code], `code sans texte : ${code}`)
  }
})

test('un code inconnu tombe sur le message par défaut, jamais sur le code brut', () => {
  assert.equal(texteErreur('code_invente_par_un_attaquant'), ERREURS.defaut)
  assert.equal(texteErreur(undefined), null)
})
