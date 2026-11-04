import { useCallback, useEffect, useState } from 'react'
import { getAdminCohortRewardWinners } from '../../api/cohortAPI'

export default function CohortRewardWinnersPanel() {
  const [cohorts, setCohorts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await getAdminCohortRewardWinners()
      setCohorts(response.data.results || [])
    } catch (requestError) {
      setError(requestError.response?.data?.detail || 'Could not load cohort winners.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  return <section className="admin-support-applications">
    <div className="contest-section-heading">
      <div>
        <div className="eyebrow">COHORT REWARDS</div>
        <h2>Cohort assessment leaders</h2>
        <p>Highest score among enrolled participants with a completed, unflagged assessment. Equal top scores are shown as a tie; no single winner is selected.</p>
      </div>
      <button className="button button-quiet" onClick={load} disabled={loading}>Refresh</button>
    </div>
    {loading ? <p>Loading cohort leaders…</p> : error ? <p role="alert">{error}</p> : cohorts.length === 0
      ? <p>No cohorts found.</p>
      : cohorts.map((cohort) => <article className="support-programme-card" key={cohort.cohort_id}>
        <div className="tutorial-card-top">
          <h3>{cohort.cohort_title}</h3>
          <span>{cohort.cohort_status.replaceAll('_', ' ')}</span>
        </div>
        {cohort.result_status === 'no_scores'
          ? <p>No eligible scored participants.</p>
          : cohort.result_status === 'tied'
            ? <p role="status">Tie: {cohort.winners.length} participants share the top score. No single winner selected.</p>
            : <p>Top-scoring participant</p>}
        {cohort.winners.map((winner) => <div className="support-programme-facts" key={winner.email}>
          <span><strong>{winner.full_name}</strong></span>
          <span>Score: {winner.score}% · {winner.assessment}</span>
          <span>Email: {winner.email}</span>
          <span>Phone: {winner.phone_number || 'Not provided'}</span>
        </div>)}
      </article>)}
  </section>
}
