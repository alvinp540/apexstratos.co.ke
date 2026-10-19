import { useState, useEffect, useRef } from 'react'

function getRemainingSeconds(startedAt, limitMinutes) {
  const deadline = new Date(startedAt).getTime() + limitMinutes * 60000
  return Math.max(0, Math.ceil((deadline - Date.now()) / 1000))
}

export default function AssessmentTimer({ limitMinutes, startedAt, onExpire }) {
  const [remaining, setRemaining] = useState(() => getRemainingSeconds(startedAt, limitMinutes))
  const onExpireRef = useRef(onExpire)

  useEffect(() => {
    onExpireRef.current = onExpire
  }, [onExpire])

  useEffect(() => {
    let expired = false
    const update = () => {
      const next = getRemainingSeconds(startedAt, limitMinutes)
      setRemaining(next)
      if (next === 0 && !expired) {
        expired = true
        onExpireRef.current?.()
      }
    }
    update()
    const id = window.setInterval(update, 1000)
    return () => window.clearInterval(id)
  }, [limitMinutes, startedAt])

  const mins = String(Math.floor(remaining / 60)).padStart(2, '0')
  const secs = String(remaining % 60).padStart(2, '0')
  const warning = remaining < 300

  return (
    <div style={{
      fontFamily: 'monospace', fontSize: '1.5rem', fontWeight: 700,
      color: warning ? 'var(--color-error)' : 'var(--color-text)',
      padding: '0.5rem 1rem', background: 'var(--color-surface)',
      borderRadius: 'var(--radius)', border: `2px solid ${warning ? 'var(--color-error)' : 'var(--color-border)'}`,
    }}>
      {mins}:{secs}
    </div>
  )
}
