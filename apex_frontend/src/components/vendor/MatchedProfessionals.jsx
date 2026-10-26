import { useState, useEffect } from 'react'
import { getJobMatches } from '../../api/vendorAPI'
import LoadingSpinner from '../common/LoadingSpinner'

export default function MatchedProfessionals({ jobId }) {
  const [matches, setMatches] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getJobMatches(jobId).then(({ data }) => setMatches(data)).catch(() => {}).finally(() => setLoading(false))
  }, [jobId])

  if (loading) return <LoadingSpinner />

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      {matches.length === 0 && <p style={{ color: 'var(--color-text-muted)' }}>No matches yet.</p>}
      {matches.map((m, i) => (
        <div key={m.professional_id} className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span style={{ fontWeight: 700, marginRight: '0.5rem' }}>#{i + 1}</span>
            {m.full_name}
            <span style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem', marginLeft: '0.5rem' }}>{m.profession}</span>
          </div>
          <span style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)', textTransform: 'capitalize' }}>{m.status?.replaceAll('_', ' ')}</span>
        </div>
      ))}
    </div>
  )
}
