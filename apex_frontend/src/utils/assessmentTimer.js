export function getRemainingSeconds(deadlineAt, serverTime, clientNow = Date.now()) {
  const deadline = Date.parse(deadlineAt)
  const serverOffset = Date.parse(serverTime) - clientNow
  if (!Number.isFinite(deadline) || !Number.isFinite(serverOffset)) return null
  return Math.max(0, Math.ceil((deadline - (clientNow + serverOffset)) / 1000))
}

export function formatRemainingTime(seconds) {
  if (!Number.isFinite(seconds)) return '--:--'
  const safeSeconds = Math.max(0, Math.floor(seconds))
  return `${String(Math.floor(safeSeconds / 60)).padStart(2, '0')}:${String(safeSeconds % 60).padStart(2, '0')}`
}
