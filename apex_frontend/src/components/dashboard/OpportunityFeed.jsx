import { useState, useEffect } from 'react'
import { getProfessionalOpportunities } from '../../api/vendorAPI'
import { formatDate, formatCurrency } from '../../utils/formatters'
import LoadingSpinner from '../common/LoadingSpinner'

export default function OpportunityFeed({ filters = {} }) {
  const [opportunities, setOpportunities] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const { profession, skill, min_merit } = filters

  useEffect(() => {
    setLoading(true)
    setError('')
    getProfessionalOpportunities({ profession, skill, min_merit })
      .then(({ data }) => setOpportunities(data.results || data))
      .catch((requestError) => {
        console.error('Could not load opportunities.', requestError)
        setError('Could not load opportunities. Please try again later.')
      })
      .finally(() => setLoading(false))
  }, [profession, skill, min_merit])

  if (loading) return <LoadingSpinner />

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      <h3>Opportunities</h3>
      {error && <p role="alert">{error}</p>}
      {opportunities.length === 0 && <p style={{ color: 'var(--color-text-muted)' }}>No active opportunities. Make sure you're available.</p>}
      {opportunities.map((opp) => (
        <div key={opp.id} className="card" style={{ borderLeft: '4px solid var(--color-accent)' }}>
          <div style={{ fontWeight: 700 }}>{opp.job?.title}</div>
          <div style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>
            {opp.job?.profession_required} · Budget: {formatCurrency(opp.job?.budget_max, opp.job?.currency)}
          </div>
          <div style={{ fontSize: '0.8rem', marginTop: '0.25rem' }}>Expires: {formatDate(opp.expires_at)}</div>
        </div>
      ))}
    </div>
  )
}
