import { useCallback, useEffect, useState } from 'react'
import Navbar from '../components/common/Navbar'
import api from '../api/axiosInstance'

export default function RewardsPage() {
  const [claims, setClaims] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState('')
  const [consentById, setConsentById] = useState({})

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get('/cohorts/rewards/')
      setClaims(Array.isArray(data) ? data : [])
    } catch (requestError) {
      setError(requestError.response?.data?.detail || 'Rewards are temporarily unavailable.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const submitClaim = async (claim) => {
    setBusyId(claim.id)
    setError('')
    try {
      await api.post(`/cohorts/rewards/${claim.id}/claim/`, {
        payment_method: 'mpesa',
        consent: true,
      })
      await load()
    } catch (requestError) {
      setError(requestError.response?.data?.detail || requestError.response?.data?.error || 'Could not submit the claim.')
    } finally {
      setBusyId('')
    }
  }

  return <>
    <Navbar />
    <main className="page-container">
      <div className="contest-section-heading">
        <div><div className="eyebrow">STUDENT REWARDS</div><h1>Rewards & payouts</h1><p>Daily KES 100 awards are based on verified participation and assessment performance. Claim review and payout confirmation are tracked separately.</p></div>
        <button className="button button-quiet" onClick={load} disabled={loading}>Refresh</button>
      </div>
      {error && <p role="alert" className="error-message">{error}</p>}
      {loading ? <p>Loading rewards…</p> : claims.length === 0 ? <section className="card"><h2>No rewards yet</h2><p>Confirmed awards will appear here after a daily settlement.</p></section> : <div className="support-programme-list">
        {claims.map((claim) => <article className="support-programme-card" key={claim.id}>
          <div className="tutorial-card-top"><span className="tag">KES {claim.amount_kes}</span><span className={`contest-status status-${claim.status}`}>{claim.status.replaceAll('_', ' ')}</span></div>
          <h2>{claim.tutorial}</h2>
          <div className="support-programme-facts">
            <span>Capability: {claim.capability}</span><span>Settlement: {claim.settlement_date}</span>
            <span>Selection: {claim.selection}</span><span>Score: {claim.score}% (rank {claim.rank})</span>
            <span>M-Pesa destination: {claim.masked_destination || 'Add a phone number to your account'}</span>
            {claim.payout_reference && <span>Provider reference: {claim.payout_reference}</span>}
            {claim.payout_confirmed_at && <span>Paid: {new Date(claim.payout_confirmed_at).toLocaleString()}</span>}
          </div>
          {claim.status === 'claim_required' && <div className="support-application-status">
            <p>Submitting confirms you want the reward reviewed for payment to your registered account phone ({claim.masked_destination}). It does not confirm a payout.</p>
            <label><input type="checkbox" checked={Boolean(consentById[claim.id])} onChange={(event) => setConsentById({ ...consentById, [claim.id]: event.target.checked })} /> I confirm this registered phone is my payout destination.</label>
            <button className="button button-primary" disabled={busyId === claim.id || !claim.masked_destination || !consentById[claim.id]} onClick={() => submitClaim(claim)}>
              {busyId === claim.id ? 'Submitting…' : 'Submit M-Pesa claim'}
            </button>
          </div>}
          {claim.rejection_reason && <p className="support-eligibility-rules">Review note: {claim.rejection_reason}</p>}
        </article>)}
      </div>}
    </main>
  </>
}
