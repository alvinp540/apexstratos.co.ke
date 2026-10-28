import { useCallback, useEffect, useState } from 'react'
import api from '../../api/axiosInstance'
import toast from 'react-hot-toast'

export default function RewardsPanel() {
  const [settlements, setSettlements] = useState([])
  const [claims, setClaims] = useState([])
  const [unassignedAdjustments, setUnassignedAdjustments] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [date, setDate] = useState('')
  const [references, setReferences] = useState({})
  const [notes, setNotes] = useState({})
  const [reasons, setReasons] = useState({})

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [settlementResponse, claimResponse] = await Promise.all([
        api.get('/cohorts/admin/rewards/settlements/'),
        api.get('/cohorts/admin/rewards/claims/'),
      ])
      setSettlements(settlementResponse.data.results || [])
      setUnassignedAdjustments(settlementResponse.data.unassigned_adjustments || [])
      setClaims(claimResponse.data)
    } catch { toast.error('Could not load reward administration data.') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const settle = async () => {
    setBusy(true)
    try {
      await api.post('/cohorts/admin/rewards/settlements/', date ? { date } : {})
      toast.success('Settlement run completed; existing daily results were left unchanged.')
      await load()
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Settlement failed.')
    } finally { setBusy(false) }
  }

  const decide = async (claim, action) => {
    const payload = { action }
    if (action === 'reject') payload.reason = reasons[claim.id]
    if (action === 'confirm_paid') {
      payload.payout_reference = references[claim.id]
      payload.reconciliation_note = notes[claim.id]
    }
    setBusy(true)
    try {
      await api.patch(`/cohorts/admin/rewards/claims/${claim.id}/`, payload)
      await load()
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Could not update this claim.')
    } finally { setBusy(false) }
  }

  return <section className="admin-support-applications">
    <div className="contest-section-heading"><div><div className="eyebrow">REWARDS & PAYOUTS</div><h2>Daily settlement review</h2><p>Students pay KES 20 to the company M-Pesa Till; an admin confirms the payment, then settlements use completed eligible merit scores.</p></div><button className="button button-quiet" onClick={load}>Refresh</button></div>
    <div className="support-programme-facts"><label>Settlement date (EAT, optional)<input type="date" value={date} onChange={(event) => setDate(event.target.value)} /></label><button className="button button-primary" disabled={busy} onClick={settle}>Settle date / yesterday</button></div>
    {loading ? <p>Loading…</p> : <>
      <h3>Settlements</h3>
      {settlements.map((row) => <article className="support-programme-card" key={row.id}>
        <h4>{row.tutorial} · {row.capability} · {row.settlement_date}</h4>
        <div className="support-programme-facts"><span>Eligible entries: {row.eligible_participant_count}</span><span>Revenue: KES {row.total_revenue_kes}</span><span>After reversals: KES {row.adjusted_revenue_kes}</span><span>Platform: KES {row.platform_share_kes} (−{row.platform_share_reversal_kes} reversed)</span><span>Rewards budget: KES {row.rewards_budget_kes} (−{row.rewards_share_reversal_kes} reversed)</span><span>Primary: {row.primary_winner_count}</span><span>Redistributed: {row.secondary_winner_count}</span><span>Awarded: KES {row.awarded_total_kes}</span><span>Reserve: KES {row.unallocated_reserve_kes}</span><span>Payment recoveries required: {row.payout_recovery_required_count}</span></div>
        {row.error_message && <p role="status">Previous settlement error (attempt {row.attempt_count}): {row.error_message}</p>}
        {row.adjustments?.map((adjustment) => <p key={adjustment.id}>Refund {adjustment.payment_reference}: KES {adjustment.refunded_amount_kes}; revenue reversal KES {adjustment.revenue_reversal_kes}; award reversal KES {adjustment.award_reversal_kes}; payout recovery {adjustment.payout_recovery_required ? 'required' : 'not required'}. {adjustment.reason}</p>)}
      </article>)}
      <h3>Student claims</h3>
      {unassignedAdjustments.length > 0 && <><h3>Refunds before settlement</h3>{unassignedAdjustments.map((adjustment) => <article className="support-programme-card" key={adjustment.id}><p>{adjustment.payment_reference} · refund ref {adjustment.refund_reference} · KES {adjustment.refunded_amount_kes} · {adjustment.reason}</p></article>)}</>}
      {claims.map((claim) => <article className="support-programme-card" key={claim.id}>
        <div className="tutorial-card-top"><strong>{claim.student_name} · {claim.student_email}</strong><span>{claim.status.replaceAll('_', ' ')}</span></div>
        <p>KES {claim.amount_kes} · {claim.tutorial} · {claim.capability} · registered phone {claim.destination_phone || 'not set'}</p>
        <p>Merit: {claim.score}% · rank {claim.rank} · {claim.selection} selection · score confirmation {claim.merit_confirmed_at ? `by ${claim.merit_confirmed_by || 'admin'} at ${new Date(claim.merit_confirmed_at).toLocaleString()}` : 'pending'}</p>
        {claim.status === 'claim_submitted' && <div><button className="button button-primary" disabled={busy} onClick={() => decide(claim, 'verify')}>Confirm merit score and approve claim</button><label>Reason if rejected<input value={reasons[claim.id] || ''} onChange={(event) => setReasons({ ...reasons, [claim.id]: event.target.value })} /></label> <button className="button button-quiet" disabled={busy || !reasons[claim.id]} onClick={() => decide(claim, 'reject')}>Reject claim</button></div>}
        {claim.status === 'verified' && <button className="button button-primary" disabled={busy} onClick={() => decide(claim, 'queue_payout')}>Mark ready for manual payout</button>}
        {claim.status === 'payout_pending' && <div className="support-application-form"><p>Complete the M-Pesa transfer manually, then record its confirmed reference and reconciliation note.</p><label>Confirmed provider reference<input value={references[claim.id] || ''} onChange={(event) => setReferences({ ...references, [claim.id]: event.target.value })} /></label><label>Reconciliation note<textarea value={notes[claim.id] || ''} onChange={(event) => setNotes({ ...notes, [claim.id]: event.target.value })} /></label><button className="button button-primary" disabled={busy || !references[claim.id] || !notes[claim.id]} onClick={() => decide(claim, 'confirm_paid')}>Confirm reconciled payment</button></div>}
      </article>)}
    </>}
  </section>
}
