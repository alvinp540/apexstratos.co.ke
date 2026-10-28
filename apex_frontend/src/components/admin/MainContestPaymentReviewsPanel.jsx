import { useCallback, useEffect, useState } from 'react'
import {
  decideMainContestPayment,
  getMainContestPaymentReviews,
} from '../../api/cohortAPI'
import { getErrorMessage, unwrapList } from '../../api/client'
import { Empty, Loading, PaginationControls } from '../States'

function formatDate(value) {
  if (!value) return 'Not provided'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? 'Not provided'
    : date.toLocaleString(undefined, { timeZone: 'Africa/Nairobi' })
}

export default function MainContestPaymentReviewsPanel() {
  const [payments, setPayments] = useState([])
  const [count, setCount] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await getMainContestPaymentReviews({ reviewable_only: 'true', page })
      setPayments(unwrapList(data))
      setCount(data?.count ?? unwrapList(data).length)
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => { load() }, [load])

  const decide = async (payment, decision, values) => {
    setBusyId(payment.id)
    setError('')
    setSuccess('')
    const payload = {
      decision,
      verification_notes: values.verification_notes.trim(),
      rejection_reason: values.rejection_reason.trim(),
    }
    if (decision === 'verified') {
      const expiresAt = new Date(values.expires_at)
      if (!values.confirmed_transaction_id.trim() || !values.expires_at || Number.isNaN(expiresAt.getTime()) || expiresAt <= new Date()) {
        setError('To accept this payment, enter the confirmed M-Pesa transaction ID and a future access expiry.')
        setBusyId('')
        return
      }
      if (!payload.verification_notes) {
        setError('Record how you checked the payment before accepting it.')
        setBusyId('')
        return
      }
      payload.confirmed_transaction_id = values.confirmed_transaction_id.trim()
      payload.expires_at = expiresAt.toISOString()
    }
    if (decision === 'rejected' && !payload.rejection_reason) {
      setError('Enter a reason before rejecting this payment.')
      setBusyId('')
      return
    }

    try {
      await decideMainContestPayment(payment.id, payload)
      setSuccess(`Payment request for ${payment.full_name || payment.email} was ${decision === 'verified' ? 'accepted' : 'rejected'}.`)
      if (payments.length === 1 && page > 1) setPage((current) => current - 1)
      else await load()
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setBusyId('')
    }
  }

  return <section className="panel admin-contest-reviews" aria-labelledby="main-contest-payment-reviews-title">
    <div className="contest-section-heading">
      <div>
        <div className="eyebrow">ADMIN ONLY · PAYMENT VERIFICATION</div>
        <h2 id="main-contest-payment-reviews-title">Main Contest M-Pesa references</h2>
        <p>Check each KES 20 payment in the company Till transactions before accepting it. Acceptance requires the confirmed transaction ID, review notes, and access expiry.</p>
      </div>
      <button className="button button-quiet" type="button" onClick={load} disabled={loading}>Refresh queue</button>
    </div>

    {success && <p role="status" className="alert alert-success">{success}</p>}
    {error && <div className="alert alert-error" role="alert">{error} <button className="text-button" type="button" onClick={load}>Refresh</button></div>}
    {loading ? <Loading label="Loading payment references…" /> : payments.length === 0
      ? error ? null : <Empty title="No payment references awaiting review">New user-submitted Main Contest references will appear here.</Empty>
      : <>
        <p aria-live="polite">{count} request{count === 1 ? '' : 's'} awaiting review</p>
        <div className="admin-contest-list">
          {payments.map((payment) => <PaymentReviewCard
            key={payment.id}
            payment={payment}
            busy={busyId === payment.id}
            onDecision={decide}
          />)}
        </div>
        <PaginationControls page={page} total={count} onPageChange={setPage} />
      </>}
  </section>
}

function PaymentReviewCard({ payment, busy, onDecision }) {
  const [values, setValues] = useState({
    confirmed_transaction_id: '',
    verification_notes: '',
    expires_at: '',
    rejection_reason: '',
  })
  const setValue = (key, value) => setValues((current) => ({ ...current, [key]: value }))

  return <article className="admin-contest-card">
    <div className="admin-contest-summary">
      <div>
        <strong>{payment.full_name || payment.email || 'Account holder'}</strong>
        <span>{payment.email} · {payment.phone_number}</span>
        <span>{payment.field} · KES {payment.amount_kes} · Till {payment.till_number}</span>
        <span>Submitted M-Pesa reference: <b>{payment.payment_reference || 'Not supplied'}</b></span>
        <small>Submitted {formatDate(payment.created_at)} · Status: {payment.status.replaceAll('_', ' ')}</small>
      </div>
    </div>
    <div className="admin-review-form">
      <label>Confirmed transaction ID<input value={values.confirmed_transaction_id} onChange={(event) => setValue('confirmed_transaction_id', event.target.value)} autoComplete="off" /></label>
      <label>Access expires at<input type="datetime-local" value={values.expires_at} onChange={(event) => setValue('expires_at', event.target.value)} /></label>
      <label>Verification notes<textarea rows="2" value={values.verification_notes} onChange={(event) => setValue('verification_notes', event.target.value)} /></label>
      <button className="button button-primary" type="button" disabled={busy} onClick={() => onDecision(payment, 'verified', values)}>{busy ? 'Saving…' : 'Accept payment'}</button>
      <label>Rejection reason<textarea rows="2" value={values.rejection_reason} onChange={(event) => setValue('rejection_reason', event.target.value)} /></label>
      <button className="button button-quiet" type="button" disabled={busy} onClick={() => onDecision(payment, 'rejected', values)}>{busy ? 'Saving…' : 'Reject payment'}</button>
    </div>
  </article>
}
