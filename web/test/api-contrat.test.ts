import { test } from 'node:test'
import assert from 'node:assert/strict'

import { ipCliente, lireCookieSession, attributsCookieSession } from '../app/api-contrat.ts'
import { etatLisible, texteErreur, ERREURS } from '../app/textes.ts'

test("ipCliente ne garde que la première IP de la chaîne", () => {
  const entetes = new Headers({ 'x-forwarded-for': '41.82.1.9, 172.18.0.4, 10.0.0.2' })
  assert.equal(ipCliente(entetes, true), '41.82.1.9')
})

test("ipCliente rend null quand l'en-tête est absent", () => {
  assert.equal(ipCliente(new Headers(), true), null)
})

test("ipCliente ignore le X-Forwarded-For tant qu'aucun proxy n'est déclaré", () => {
  // Le cas RÉEL aujourd'hui : rien ne se tient devant `web`. L'en-tête ne peut
  // donc venir que du client lui-même ; le relayer laisserait n'importe qui
  // contourner les plafonds par IP en faisant tourner la valeur.
  const forge = new Headers({ 'x-forwarded-for': '1.2.3.4' })
  assert.equal(ipCliente(forge, false), null)
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

test("chaque état de users.state a un libellé, et jamais la valeur brute", () => {
  // La liste fait foi dans USER_STATES (src/db/models.py). Si elle y gagne une
  // valeur sans que ce fichier suive, le repli parle encore français.
  for (const etat of ['onboarding', 'active', 'blocked']) {
    const libelle = etatLisible(etat)
    assert.ok(libelle, `état sans libellé : ${etat}`)
    assert.notEqual(libelle, etat, `libellé brut affiché pour ${etat}`)
  }
  assert.equal(etatLisible('valeur_ajoutee_plus_tard'), 'État inconnu')
})
