import assert from 'node:assert/strict'
import test from 'node:test'
import { formatRemainingTime, getRemainingSeconds } from './assessmentTimer.js'

const clientNow = Date.parse('2026-10-28T08:00:00.000Z')
const serverTime = new Date(clientNow).toISOString()

test('counts down from the backend deadline with an HH:MM display', () => {
  assert.equal(getRemainingSeconds('2026-10-28T08:04:59.000Z', serverTime, clientNow), 299)
  assert.equal(formatRemainingTime(299), '04:59')
  assert.equal(formatRemainingTime(205), '03:25')
  assert.equal(formatRemainingTime(30), '00:30')
})

test('refreshing with the same backend deadline restores remaining time without resetting', () => {
  const deadline = '2026-10-28T08:03:25.000Z'
  const refreshedAt = Date.parse('2026-10-28T08:01:00.000Z')
  const refreshedServerTime = new Date(refreshedAt).toISOString()
  assert.equal(formatRemainingTime(getRemainingSeconds(deadline, refreshedServerTime, refreshedAt)), '02:25')
})

test('an expired backend deadline stays at zero and invalid timestamps are unavailable', () => {
  assert.equal(getRemainingSeconds(serverTime, serverTime, clientNow), 0)
  assert.equal(getRemainingSeconds('invalid', serverTime, clientNow), null)
  assert.equal(formatRemainingTime(null), '--:--')
})
