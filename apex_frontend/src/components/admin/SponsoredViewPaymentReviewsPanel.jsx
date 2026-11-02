import { useCallback, useEffect, useState } from 'react'
import api, { getErrorMessage, unwrapList } from '../../api/client'
import { Empty, Loading } from '../States'

function formatDate(value) {
  if (!value) return 'Not provided'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? 'Not provided'
    : date.toLocaleString(undefined, { timeZone: 'Africa/Nairobi' })
}

export default function SponsoredViewPaymentReviewsPanel() {
  const [payments, setPayments] = useState([])
  const [transactionIds, setTransactionIds] = useState({})
  const [rejectionReasons, setRejectionReasons] = useState({})
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get('/cohorts/admin/sponsored-view/payments/')
      setPayments(unwrapList(data))
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const decide = async (payment, decision) => {
    const transactionId = (transactionIds[payment.id] || '').trim()
    const reason = (rejectionReasons[payment.id] || '').trim()
    if (decision === 'verified' && !transactionId) {
      setError('Enter the confirmed M-Pesa transaction ID before verifying payment.')
      return
    }
    if (['rejected', 'refunded'].includes(decision) && !reason) {
      setError(`Enter a reason before ${decision === 'refunded' ? 'recording a refund' : 'rejecting this payment'}.`)
      return
    }
    if (decision === 'refunded' && !transactionId) {
      setError('Enter the confirmed M-Pesa refund reference before recording a refund.')
      return
    }

    setBusyId(payment.id)
    setError('')
    setSuccess('')
    try {
      await api.post(`/cohorts/admin/sponsored-view/payments/${payment.id}/decision/`, {
        status: decision,
        mpesa_transaction_id: decision === 'verified' ? transactionId : '',
        rejection_reason: reason,
        refund_reference: decision === 'refunded' ? transactionId : '',
      })
      setSuccess(`Payment for ${payment.student_name || payment.student_email} was ${decision}.`)
      await load()
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setBusyId('')
    }
  }

  const pendingPayments = payments.filter((payment) => payment.status === 'pending')
  const verifiedPayments = payments.filter((payment) => payment.status === 'verified')

  return <section className="panel admin-support-applications" aria-labelledby="sponsored-view-payment-reviews-title">
    <div className="contest-section-heading">
      <div>
        <div className="eyebrow">ADMIN ONLY · PAYMENT VERIFICATION</div>
        <h2 id="sponsored-view-payment-reviews-title">Sponsored View payments</h2>
        <p>Check the submitted tier amount and payment reference against the company Till transaction. Verification grants access to the assessment.</p>
      </div>
      <button className="button button-quiet" type="button" onClick={load} disabled={loading}>Refresh queue</button>
    </div>
    {success && <p role="status" className="alert alert-success">{success}</p>}
    {error && <div className="alert alert-error" role="alert">{error}</div>}
    {loading ? <Loading label="Loading Sponsored View payment reviews…" /> : error && payments.length === 0 ? null : <>
      <div className="panel-heading"><h3>Awaiting review</h3><span className="soft-label">{pendingPayments.length} pending</span></div>
      {pendingPayments.length
        ? <div className="support-application-list">{pendingPayments.map((payment) => <PaymentReviewCard
          key={payment.id}
          payment={payment}
          transactionId={transactionIds[payment.id] || ''}
          rejectionReason={rejectionReasons[payment.id] || ''}
          busy={busyId === payment.id}
          onTransactionIdChange={(value) => setTransactionIds((current) => ({ ...current, [payment.id]: value }))}
          onRejectionReasonChange={(value) => setRejectionReasons((current) => ({ ...current, [payment.id]: value }))}
          onDecision={decide}
        />)}</div>
        : <Empty title="No Sponsored View payments awaiting review" />}
      {verifiedPayments.length > 0 && <>
        <div className="panel-heading"><h3>Verified payments</h3><span className="soft-label">{verifiedPayments.length} verified</span></div>
        <div className="support-application-list">{verifiedPayments.map((payment) => <PaymentReviewCard
          key={payment.id}
          payment={payment}
          transactionId={transactionIds[payment.id] || ''}
          rejectionReason={rejectionReasons[payment.id] || ''}
          busy={busyId === payment.id}
          onTransactionIdChange={(value) => setTransactionIds((current) => ({ ...current, [payment.id]: value }))}
          onRejectionReasonChange={(value) => setRejectionReasons((current) => ({ ...current, [payment.id]: value }))}
          onDecision={decide}
        />)}</div>
      </>}
    </>}
  </section>
}

function PaymentReviewCard({
  payment,
  transactionId,
  rejectionReason,
  busy,
  onTransactionIdChange,
  onRejectionReasonChange,
  onDecision,
}) {
  return <article className="support-application-status">
    <strong>{payment.student_name || payment.student_email} · {payment.assessment_title}</strong>
    <span>{payment.status} · KSh {payment.amount_kes} · Till {payment.till_number}</span>
    <small>{payment.student_email} · {payment.field} · Submitted reference: {payment.payment_reference}</small>
    <small>Requested {formatDate(payment.requested_at)}{payment.verified_at ? ` · Verified ${formatDate(payment.verified_at)}` : ''}</small>
    {payment.status === 'pending' && <div className="form-stack">
      <label>Confirmed M-Pesa transaction ID<input required value={transactionId} onChange={(event) => onTransactionIdChange(event.target.value)} autoComplete="off" /></label>
      <button className="button button-primary" type="button" disabled={busy} onClick={() => onDecision(payment, 'verified')}>{busy ? 'Saving…' : 'Verify payment and grant access'}</button>
      <label>Rejection reason<input required value={rejectionReason} onChange={(event) => onRejectionReasonChange(event.target.value)} /></label>
      <button className="button button-quiet" type="button" disabled={busy} onClick={() => onDecision(payment, 'rejected')}>{busy ? 'Saving…' : 'Reject payment'}</button>
    </div>}
    {payment.status === 'verified' && <div className="form-stack">
      <label>Confirmed M-Pesa refund reference<input required value={transactionId} onChange={(event) => onTransactionIdChange(event.target.value)} autoComplete="off" /></label>
      <label>Refund reason<input required value={rejectionReason} onChange={(event) => onRejectionReasonChange(event.target.value)} /></label>
      <button className="button button-quiet" type="button" disabled={busy || !transactionId.trim() || !rejectionReason.trim()} onClick={() => onDecision(payment, 'refunded')}>{busy ? 'Saving…' : 'Record confirmed refund'}</button>
    </div>}
  </article>
}
