import { useState, useEffect, useRef } from 'react'
import { formatRemainingTime, getRemainingSeconds } from '../../utils/assessmentTimer'

export default function AssessmentTimer({ deadlineAt, serverTime, onExpire }) {
  const [remaining, setRemaining] = useState(() => getRemainingSeconds(deadlineAt, serverTime))
  const onExpireRef = useRef(onExpire)

  useEffect(() => {
    onExpireRef.current = onExpire
  }, [onExpire])

  useEffect(() => {
    let expired = false
    const update = () => {
      const next = getRemainingSeconds(deadlineAt, serverTime)
      setRemaining(next)
      if (next === 0 && !expired) {
        expired = true
        onExpireRef.current?.()
      }
    }
    if (!deadlineAt || !serverTime) {
      setRemaining(null)
      return undefined
    }
    update()
    const id = window.setInterval(update, 1000)
    return () => window.clearInterval(id)
  }, [deadlineAt, serverTime])

  const warning = remaining !== null && remaining <= 60
  const critical = remaining !== null && remaining <= 30

  return (
    <div style={{
      fontFamily: 'monospace', fontSize: '1.5rem', fontWeight: 700,
      color: warning ? 'var(--color-error)' : 'var(--color-text)',
      padding: '0.5rem 1rem', background: 'var(--color-surface)',
      borderRadius: 'var(--radius)', border: `2px solid ${warning ? 'var(--color-error)' : 'var(--color-border)'}`,
    }}>
      {formatRemainingTime(remaining)}
      {critical && <span role="alert" style={{ display: 'block', fontSize: '0.75rem' }}>30 seconds remaining</span>}
      {warning && !critical && <span role="status" style={{ display: 'block', fontSize: '0.75rem' }}>One minute remaining</span>}
    </div>
  )
}
