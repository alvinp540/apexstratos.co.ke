import { useState, useEffect } from 'react'
import { getCohortLeaderboard } from '../../api/cohortAPI'
import LoadingSpinner from '../common/LoadingSpinner'

export default function CohortLeaderboard({ cohortId }) {
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getCohortLeaderboard(cohortId)
      .then(({ data }) => setEntries(data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [cohortId])

  if (loading) return <LoadingSpinner />

  return (
    <div>
      {entries.map((e) => (
        <div key={e.user_id} style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '0.6rem 0', borderBottom: '1px solid var(--color-border)',
        }}>
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
            <span style={{
              fontWeight: 700, fontSize: '1rem',
              color: e.rank <= 3 ? 'var(--color-warning)' : 'var(--color-text-muted)',
              width: '2rem', textAlign: 'center',
            }}>#{e.rank}</span>
            <span>{e.full_name}</span>
          </div>
          <span style={{ fontWeight: 700, color: 'var(--color-primary)' }}>{e.score?.toFixed(1)}%</span>
        </div>
      ))}
      {entries.length === 0 && <p style={{ color: 'var(--color-text-muted)' }}>No results yet.</p>}
    </div>
  )
}
