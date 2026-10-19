import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import Page from '../components/Page'
import { Empty, ErrorState, Loading } from '../components/States'
import WeeklyScheduleNotice from '../components/WeeklyScheduleNotice'
import { useAuth } from '../context/AuthContext'
import { studyAreas } from '../data'
import {
  decideMainContestPayment,
  getMainContestAssessments,
  getMainContestLibrary,
  getMainContestPaymentReviews,
  getMainContestPayments,
  getMyContestCycleLeaderboard,
  saveMainContestAttemptAnswers,
  startMainContestAssessment,
  submitMainContestAttempt,
  submitMainContestPayment,
} from '../api/cohortAPI'
import { getErrorMessage, unwrapList } from '../api/client'

function formatDate(value) {
  if (!value) return 'Not provided'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Not provided' : date.toLocaleString(undefined, { timeZone: 'Africa/Nairobi' })
}

function contestDay(value) {
  return ({ 4: 'FRIDAY', 5: 'SATURDAY', 6: 'SUNDAY' })[value] || 'CONTEST DAY'
}

function useContestCountdown(attempt, onExpire) {
  const [remaining, setRemaining] = useState(null)
  useEffect(() => {
    if (!attempt?.id) {
      setRemaining(null)
      return undefined
    }
    const deadline = Date.parse(attempt.deadline_at)
    const serverTime = Date.parse(attempt.server_time)
    if (!Number.isFinite(deadline) || !Number.isFinite(serverTime)) {
      setRemaining(null)
      return undefined
    }
    const serverOffset = serverTime - Date.now()
    let expired = false
    const update = () => {
      const seconds = Math.max(0, Math.ceil((deadline - (Date.now() + serverOffset)) / 1000))
      setRemaining(seconds)
      if (seconds === 0 && !expired) {
        expired = true
        onExpire()
      }
    }
    update()
    const timer = window.setInterval(update, 1000)
    return () => window.clearInterval(timer)
  }, [attempt?.id, attempt?.deadline_at, attempt?.server_time, onExpire])
  if (remaining === null) return '—'
  return `${String(Math.floor(remaining / 60)).padStart(2, '0')}:${String(remaining % 60).padStart(2, '0')}`
}

export default function ContestPage() {
  const { user } = useAuth()
  const [profile, setProfile] = useState(null)
  const [payments, setPayments] = useState([])
  const [contests, setContests] = useState([])
  const [libraryItems, setLibraryItems] = useState([])
  const [libraryCount, setLibraryCount] = useState(0)
  const [libraryFilters, setLibraryFilters] = useState({ field: '', week: '', topic: '' })
  const [libraryLoading, setLibraryLoading] = useState(true)
  const [libraryError, setLibraryError] = useState('')
  const [cycleStanding, setCycleStanding] = useState(null)
  const [adminPayments, setAdminPayments] = useState([])
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(true)
  const [activeAssessment, setActiveAssessment] = useState(null)
  const [activeAttempt, setActiveAttempt] = useState(null)
  const [answers, setAnswers] = useState({})
  const [reasoning, setReasoning] = useState({})
  const [paymentForm, setPaymentForm] = useState({ full_name: '', field: '', payment_reference: '' })
  const [paymentSubmitted, setPaymentSubmitted] = useState(false)
  const [paymentBusy, setPaymentBusy] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [reviewBusy, setReviewBusy] = useState('')
  const answersRef = useRef({})
  const reasoningRef = useRef({})
  const activeRef = useRef(null)
  const expiredRef = useRef(false)

  const updateAnswers = (next) => {
    answersRef.current = next
    setAnswers(next)
  }

  const updateReasoning = (next) => {
    reasoningRef.current = next
    setReasoning(next)
  }

  const load = useCallback(async () => {
    setLoading(true)
    const requests = [
      ['profile', () => import('../api/profileAPI').then(({ getMyProfile }) => getMyProfile())],
      ['payments', getMainContestPayments],
      ['contests', getMainContestAssessments],
      ['cycleStanding', getMyContestCycleLeaderboard],
    ]
    if (user?.is_admin) requests.push(['adminPayments', getMainContestPaymentReviews])
    const results = await Promise.all(requests.map(async ([key, request]) => {
      try {
        const { data } = await request()
        return [key, data, '']
      } catch (error) {
        return [key, null, getErrorMessage(error)]
      }
    }))
    const resultMap = Object.fromEntries(results.map(([key, data]) => [key, data]))
    const nextErrors = Object.fromEntries(results.filter(([, , error]) => error).map(([key, , error]) => [key, error]))
    setProfile(resultMap.profile || null)
    if (resultMap.profile?.full_name) {
      setPaymentForm((current) => ({ ...current, full_name: current.full_name || resultMap.profile.full_name }))
    }
    setPayments(unwrapList(resultMap.payments))
    setContests(unwrapList(resultMap.contests))
    setCycleStanding(resultMap.cycleStanding || null)
    setAdminPayments(unwrapList(resultMap.adminPayments))
    setErrors(nextErrors)
    setLoading(false)
  }, [user?.is_admin])

  useEffect(() => { load() }, [load])

  const loadLibrary = useCallback(async () => {
    setLibraryLoading(true)
    setLibraryError('')
    try {
      const params = Object.fromEntries(
        Object.entries({
          field: libraryFilters.field,
          week: libraryFilters.week,
          topic: libraryFilters.topic,
        }).filter(([, value]) => value),
      )
      const { data } = await getMainContestLibrary(params)
      setLibraryItems(unwrapList(data))
      setLibraryCount(data?.count ?? unwrapList(data).length)
    } catch (error) {
      setLibraryError(getErrorMessage(error))
    } finally {
      setLibraryLoading(false)
    }
  }, [libraryFilters.field, libraryFilters.week, libraryFilters.topic])

  useEffect(() => { loadLibrary() }, [loadLibrary])

  const refreshContests = useCallback(async () => {
    try {
      const { data } = await getMainContestAssessments()
      setContests(unwrapList(data))
      setErrors((current) => {
        const next = { ...current }
        delete next.contests
        return next
      })
    } catch (error) {
      setErrors((current) => ({ ...current, contests: getErrorMessage(error) }))
    }
    try {
      const { data } = await getMyContestCycleLeaderboard()
      setCycleStanding(data)
      setErrors((current) => {
        const next = { ...current }
        delete next.cycleStanding
        return next
      })
    } catch (error) {
      setErrors((current) => ({ ...current, cycleStanding: getErrorMessage(error) }))
    }
  }, [])

  const closeAttempt = useCallback(() => {
    setActiveAttempt(null)
    activeRef.current = null
    expiredRef.current = false
    updateAnswers({})
    updateReasoning({})
  }, [])

  const expireAttempt = useCallback(async () => {
    if (!activeRef.current || expiredRef.current) return
    expiredRef.current = true
    setSubmitting(true)
    let terminal = false
    try {
      await submitMainContestAttempt(activeRef.current.id, answersRef.current, reasoningRef.current)
      terminal = true
    } catch (error) {
      terminal = error.response?.status === 410 || error.response?.status === 409
      if (!terminal) {
        setErrors((current) => ({ ...current, attempt: getErrorMessage(error) }))
        expiredRef.current = false
      }
    } finally {
      await refreshContests()
      if (terminal) closeAttempt()
      setSubmitting(false)
    }
  }, [closeAttempt, refreshContests])

  const timer = useContestCountdown(activeAttempt, expireAttempt)

  const activeAttemptId = activeAttempt?.id
  const activeAttemptStatus = activeAttempt?.status
  useEffect(() => {
    if (!activeAttemptId || activeAttemptStatus !== 'in_progress' || submitting) return undefined
    const saveTimer = window.setTimeout(() => {
      saveMainContestAttemptAnswers(activeAttemptId, answers, reasoning)
        .catch((error) => {
          if (![409, 410].includes(error.response?.status)) {
            setErrors((current) => ({ ...current, attempt: getErrorMessage(error) }))
          }
        })
    }, 500)
    return () => window.clearTimeout(saveTimer)
  }, [activeAttemptId, activeAttemptStatus, answers, reasoning, submitting])

  const openAttempt = (assessment, attempt) => {
    if (!attempt?.id || !attempt.deadline_at || !attempt.server_time) {
      setErrors((current) => ({ ...current, attempt: 'The server did not return a usable attempt deadline. Reload the contest list before continuing.' }))
      return
    }
    setErrors((current) => {
      const next = { ...current }
      delete next.attempt
      return next
    })
    expiredRef.current = false
    activeRef.current = attempt
    setActiveAssessment(assessment)
    setActiveAttempt(attempt)
    updateAnswers(attempt.answers || {})
    updateReasoning(attempt.reasoning || {})
  }

  const startContest = async (assessment) => {
    setErrors((current) => {
      const next = { ...current }
      delete next.attempt
      return next
    })
    try {
      const { data } = await startMainContestAssessment(assessment.id)
      openAttempt(assessment, data)
      await refreshContests()
    } catch (error) {
      setErrors((current) => ({ ...current, attempt: getErrorMessage(error) }))
      await refreshContests()
    }
  }

  const submitAnswers = async () => {
    if (!activeAttempt || !activeAssessment || timer === '00:00' || timer === '—') return
    setSubmitting(true)
    try {
      const { data } = await submitMainContestAttempt(activeAttempt.id, answers, reasoning)
      setContests((current) => current.map((contest) => contest.id === activeAssessment.id
        ? { ...contest, attempt: { ...contest.attempt, ...data } }
        : contest))
      closeAttempt()
      await refreshContests()
    } catch (error) {
      setErrors((current) => ({ ...current, attempt: getErrorMessage(error) }))
      if (error.response?.status === 410) closeAttempt()
    } finally {
      setSubmitting(false)
    }
  }

  const submitPayment = async (event) => {
    event.preventDefault()
    setPaymentSubmitted(false)
    setErrors((current) => {
      const next = { ...current }
      delete next.paymentSubmit
      return next
    })
    setPaymentBusy(true)
    try {
      const phone = user?.phone_number || profile?.phone_number || ''
      await submitMainContestPayment({
        full_name: paymentForm.full_name.trim(),
        phone_number: phone,
        field: paymentForm.field,
        program: 'main_contest',
        amount_kes: 100,
        payment_reference: paymentForm.payment_reference.trim(),
      })
      setPaymentSubmitted(true)
      setPaymentForm((current) => ({ ...current, payment_reference: '' }))
    } catch (error) {
      setErrors((current) => ({ ...current, paymentSubmit: getErrorMessage(error) }))
      setPaymentBusy(false)
      return
    }
    try {
      const { data } = await getMainContestPayments()
      setPayments(unwrapList(data))
      setErrors((current) => {
        const next = { ...current }
        delete next.payments
        return next
      })
    } catch (error) {
      setErrors((current) => ({ ...current, payments: getErrorMessage(error) }))
    } finally {
      setPaymentBusy(false)
    }
  }

  const reviewPayment = async (paymentId, form) => {
    setReviewBusy(paymentId)
    setErrors((current) => {
      const next = { ...current }
      delete next.adminDecision
      return next
    })
    const payload = {
      decision: form.decision,
      verification_notes: form.verification_notes.trim(),
    }
    if (form.decision === 'verified') {
      const expiry = new Date(form.expires_at)
      if (!form.expires_at || Number.isNaN(expiry.getTime()) || expiry <= new Date()) {
        setErrors((current) => ({ ...current, adminDecision: 'Set a future access expiry before verifying this payment.' }))
        setReviewBusy('')
        return
      }
      payload.confirmed_transaction_id = form.confirmed_transaction_id.trim()
      payload.expires_at = expiry.toISOString()
    }
    if (form.decision === 'rejected') payload.rejection_reason = form.rejection_reason.trim()
    try {
      await decideMainContestPayment(paymentId, payload)
      const { data } = await getMainContestPaymentReviews()
      setAdminPayments(unwrapList(data))
    } catch (error) {
      setErrors((current) => ({ ...current, adminDecision: getErrorMessage(error) }))
    } finally {
      setReviewBusy('')
    }
  }

  const phone = user?.phone_number || profile?.phone_number || ''

  return <Page eyebrow="PRACTICE & CHALLENGE" title="Main contests" description="Contest assessments and payment requests shown here come from Apex. The server controls access, contest windows, attempt deadlines, and scores.">
    <section className="panel contest-library-panel">
      <div className="contest-section-heading"><div><div className="eyebrow">MAIN CONTEST LIBRARY</div><h2>KSh 100 per applicable access period</h2><p>Each published assessment contains ten questions. Payment verification grants field-specific access; the 20-minute timer starts only when the server accepts your start action during the Friday–Sunday window.</p></div><span className="contest-price">{libraryCount} matching</span></div>
      <WeeklyScheduleNotice activity="main_contest" />
      <div className="filter-row"><label>Study area<select value={libraryFilters.field} onChange={(event) => setLibraryFilters((current) => ({ ...current, field: event.target.value }))}><option value="">All study areas</option>{studyAreas.map((field) => <option value={field} key={field}>{field}</option>)}</select></label><label>Week<select value={libraryFilters.week} onChange={(event) => setLibraryFilters((current) => ({ ...current, week: event.target.value }))}><option value="">All 8 weeks</option>{Array.from({ length: 8 }, (_, index) => <option key={index + 1} value={index + 1}>Week {index + 1}</option>)}</select></label><label>Topic<input maxLength={120} value={libraryFilters.topic} onChange={(event) => setLibraryFilters((current) => ({ ...current, topic: event.target.value }))} placeholder="Search titles and descriptions" /></label><button className="button button-quiet" onClick={loadLibrary}>↻ Refresh library</button></div>
      {libraryError ? <ErrorState message={libraryError} retry={loadLibrary} /> : libraryLoading ? <Loading label="Loading published main-contest assessments…" /> : libraryItems.length === 0 ? <Empty title="0 complete assessments are currently published">The database currently contains no published main-contest assessment with ten valid multiple-choice questions. Target: 720 assessments / 7,200 questions.</Empty> : <div className="content-grid">{libraryItems.map((assessment) => {
        const locked = !assessment.has_verified_access && assessment.attempt?.status !== 'in_progress' && assessment.attempt?.status !== 'graded'
        return <article className="tutorial-card" key={assessment.id}>
          <div className="tutorial-card-top"><span className="tag">{assessment.field}</span><span className="tag">Week {assessment.week}</span></div>
          <div className={`assessment-preview${locked ? ' assessment-preview-locked' : ''}`} aria-hidden={locked || undefined}>
            <h3>{assessment.title}</h3><p>{assessment.description}</p>
          </div>
          {locked && <p className="assessment-lock-notice" role="status">Preview locked until your KSh 100 payment is verified for this study area. <a href="#contest-payment-form">Go to payment form.</a></p>}
          <div className="tutorial-meta"><span>10 questions · 20 minutes · KSh {assessment.access_price_kes}</span><span>{assessment.attempt?.status === 'graded' ? `Completed · ${assessment.attempt.score}%` : assessment.attempt?.status === 'timed_out' ? 'Attempt expired' : assessment.can_start ? 'Available now · EAT' : `Next opening: ${formatDate(assessment.next_opening_at)}`}</span></div>
          {(!assessment.attempt || assessment.attempt.status === 'in_progress') && <button className="button button-primary" disabled={!assessment.can_start} onClick={() => startContest(assessment)}>{assessment.attempt?.status === 'in_progress' ? 'Resume assessment' : assessment.can_start ? 'Start assessment' : locked ? 'Requires verified payment and Friday–Sunday access' : 'Available Friday–Sunday'}</button>}
          {assessment.attempt?.status === 'graded' && assessment.attempt.questions?.length > 0 && <details className="contest-answer-review"><summary>Review answers and explanations</summary><ol>{assessment.attempt.questions.map((question) => <li key={question.id}><strong>{question.prompt}</strong><p>Your answer: {question.selected_answer || 'No answer submitted'}</p><p>Correct answer: {question.correct_answer}</p><p>{question.rationale}</p></li>)}</ol></details>}
        </article>
      })}</div>}
    </section>
    <section className="panel contest-payment-panel">
      <div className="contest-section-heading"><div><div className="eyebrow">MAIN CONTEST ACCESS</div><h2>Payment review</h2><p>Submit your KSh 100 M-Pesa reference for the official study area you want to enter. Payment is reviewed by an administrator and does not add merit.</p></div><span className="contest-price">KES 100</span></div>
      {errors.profile && <div className="alert alert-error" role="alert">Profile details could not be loaded. Your registered phone and name will be validated by the server when you submit.</div>}
      {errors.payments && <ErrorState message={errors.payments} retry={load} />}
      <div className="contest-payment-layout">
        <form id="contest-payment-form" className="contest-payment-form" onSubmit={submitPayment}>
          {errors.paymentSubmit && <div className="alert alert-error" role="alert">{errors.paymentSubmit}</div>}
          {paymentSubmitted && <div className="alert alert-success" role="status">Payment reference submitted. It will remain pending until reviewed by an administrator.</div>}
          <label>Full name on your Apex profile<input value={paymentForm.full_name} onChange={(event) => setPaymentForm({ ...paymentForm, full_name: event.target.value })} required autoComplete="name" /></label>
          <label>Registered phone number<input value={phone} readOnly aria-describedby="contest-phone-note" placeholder="Add a phone number to your profile first" /></label>
          <small id="contest-phone-note" className="contest-help">{phone ? 'This number is sent as registered and cannot be changed here.' : <>Add a phone number to your <Link to="/profile">profile</Link> before submitting payment.</>}</small>
          <label>Official study area<select value={paymentForm.field} onChange={(event) => setPaymentForm({ ...paymentForm, field: event.target.value })} required><option value="">Choose a study area</option>{studyAreas.map((field) => <option value={field} key={field}>{field}</option>)}</select></label>
          <label>M-Pesa transaction reference<input value={paymentForm.payment_reference} onChange={(event) => setPaymentForm({ ...paymentForm, payment_reference: event.target.value })} required minLength={5} autoComplete="off" /></label>
          <div className="contest-payment-instructions"><strong>Pay KSh 100 to the official Apex Till.</strong><span>Use Till number 1598106. Keep your transaction confirmation; an admin verifies the reference before the platform makes contest assessments available.</span></div>
          <button className="button button-primary" disabled={paymentBusy || !phone}>{paymentBusy ? 'Submitting…' : 'Submit payment reference'} <span>↗</span></button>
        </form>
        <div className="contest-payment-status"><div className="panel-heading"><h3>Your payment requests</h3>{!loading && <button className="text-button" onClick={load}>↻ Refresh</button>}</div>
          {loading ? <Loading label="Loading payment requests…" /> : errors.payments ? null : payments.length === 0 ? <Empty title="No payment requests yet">Submitted references and their review status will appear here.</Empty> : <div className="contest-payment-list">{payments.map((payment) => <article className="contest-payment-item" key={payment.id}><div><strong>{payment.field}</strong><span>{payment.payment_reference || 'Reference not listed'} · KES {payment.amount_kes}</span><small>Submitted {formatDate(payment.created_at)}</small></div><span className={`contest-status status-${payment.status}`}>{payment.status?.replaceAll('_', ' ') || 'status unavailable'}</span>{payment.rejection_reason && <p>{payment.rejection_reason}</p>}</article>)}</div>}
        </div>
      </div>
    </section>

    {activeAttempt && activeAssessment ? <ContestAttempt assessment={activeAssessment} attempt={activeAttempt} answers={answers} reasoning={reasoning} onAnswer={(questionId, answer) => updateAnswers({ ...answersRef.current, [questionId]: answer })} onReasoning={(questionId, text) => updateReasoning({ ...reasoningRef.current, [questionId]: text })} onSubmit={submitAnswers} onExit={closeAttempt} onExpireRetry={expireAttempt} timer={timer} submitting={submitting} error={errors.attempt} /> : <section className="contest-assessment-section">
      <div className="contest-section-heading"><div><div className="eyebrow">ASSESSMENT WINDOW</div><h2>Contest assessments and results</h2><p>Published assessments and previous results remain visible. New attempts can only start Friday through Sunday EAT after field-specific payment verification.</p></div><button className="button button-quiet" onClick={refreshContests}>↻ Refresh</button></div>
      <div className="contest-cycle-standing" aria-live="polite">
        <div><div className="eyebrow">WEEKLY MAIN CONTEST STANDING</div><strong>{cycleStanding?.rank ? `#${cycleStanding.rank}` : cycleStanding?.rank === null ? 'No rank yet' : 'Loading standing…'}</strong></div>
        {errors.cycleStanding ? <p role="alert">{errors.cycleStanding}</p> : cycleStanding?.rank == null ? <p>Complete a verified, unflagged Main Contest assessment to appear in the provisional weekly standings.</p> : <div className="contest-cycle-details">
          <span>{cycleStanding.field} · {cycleStanding.ranking_status}</span>
          <span>{cycleStanding.average_score}% average · {cycleStanding.participant_count} participants</span>
          <span>{formatDate(cycleStanding.cycle_start)} – {formatDate(cycleStanding.cycle_end)}</span>
          {cycleStanding.tie_break_applied && cycleStanding.tie_break_seconds != null && <span>Equivalent-assessment tie-break: {cycleStanding.tie_break_seconds} seconds</span>}
        </div>}
        <p className="contest-cycle-disclaimer">Provisional Friday–Sunday standing only; it is not a finalized four-week Merit cycle or a promise of an award or payout.</p>
      </div>
      {errors.attempt && <div className="alert alert-error" role="alert">{errors.attempt}</div>}
      {errors.contests ? <ErrorState message={errors.contests} retry={refreshContests} /> : loading ? <Loading label="Loading published assessments and results…" /> : contests.length === 0 ? <Empty title="No published assessments or previous results">There are no published main-contest assessments for verified fields or previous attempts on this account.</Empty> : <div className="content-grid contest-card-grid">{contests.map((assessment) => <ContestCard key={assessment.id} assessment={assessment} onStart={startContest} onResume={openAttempt} />)}</div>}
    </section>}

    {user?.is_admin && <AdminPaymentReviews payments={adminPayments} loading={loading} error={errors.adminPayments || errors.adminDecision} onRetry={load} onReview={reviewPayment} busyId={reviewBusy} />}
  </Page>
}

function ContestCard({ assessment, onStart, onResume }) {
  const attempt = assessment.attempt
  const submitted = attempt?.status === 'graded'
  const inProgress = attempt?.status === 'in_progress'
  return <article className="contest-card">
    <div className="contest-card-top"><span className="tag">{assessment.field}</span><span className="contest-slot">{contestDay(assessment.day)} · SLOT {assessment.assessment_slot}</span></div>
    <h3>{assessment.title}</h3><p>{assessment.description}</p>
    <div className="contest-facts"><span>{assessment.duration_minutes} minutes</span><span>{assessment.can_start ? `Window closes ${formatDate(assessment.window_closes_at)}` : `Next opening ${formatDate(assessment.next_opening_at)}`}</span></div>
    {submitted && <div className="contest-result"><span>Server result</span><strong>{attempt.score ?? '—'}%</strong><small>{attempt.is_flagged ? 'Flagged for review' : 'Submitted'} · {formatDate(attempt.submitted_at)}</small></div>}
    {attempt && !inProgress && !submitted && <div className="contest-expired">Attempt status: {attempt.status?.replaceAll('_', ' ') || 'unavailable'}. This attempt cannot be restarted.</div>}
    {inProgress ? <button className="button button-primary" disabled={!assessment.can_start} onClick={() => onResume(assessment, attempt)}>Resume attempt <span>↗</span></button> : !attempt && <button className="button button-primary" disabled={!assessment.can_start} onClick={() => onStart(assessment)}>{assessment.can_start ? 'Start assessment' : 'Opens Friday' } <span>↗</span></button>}
  </article>
}

function ContestAttempt({ assessment, attempt, answers, reasoning, onAnswer, onReasoning, onSubmit, onExit, onExpireRetry, timer, submitting, error }) {
  const deadlineUnavailable = timer === '—'
  const expired = timer === '00:00'
  const missingReasoning = attempt.questions?.some((question) => question.requires_reasoning && !reasoning[question.id]?.trim())
  return <section className="panel contest-attempt">
    <div className="contest-attempt-heading"><div><div className="eyebrow">{assessment.field} · LIVE ATTEMPT</div><h2>{attempt.title || assessment.title}</h2><p>{attempt.description || assessment.description}</p></div><div className={`contest-timer${expired ? ' timer-expired' : ''}`}><small>SERVER DEADLINE</small><strong>{timer}</strong><span>{formatDate(attempt.deadline_at)}</span></div></div>
    {error && <div className="alert alert-error" role="alert">{error}</div>}
    {deadlineUnavailable && <div className="alert alert-error" role="alert">A server deadline was not provided, so this attempt cannot be answered safely. Reload the contest list or contact support.</div>}
    {attempt.questions?.length ? <div className="contest-question-list">{attempt.questions.map((question, index) => <fieldset key={question.id} className="contest-question" disabled={expired || deadlineUnavailable || submitting}><legend><span>QUESTION {index + 1} OF {attempt.questions.length}</span>{question.prompt}</legend><div className="contest-options">{(question.options || []).map((option, optionIndex) => {
      const value = String(option)
      return <label className={answers[question.id] === value ? 'selected' : ''} key={`${question.id}-${optionIndex}`}><input type="radio" name={`contest-question-${question.id}`} value={value} checked={answers[question.id] === value} onChange={() => onAnswer(question.id, value)} /><span>{value}</span></label>
    })}</div>{question.requires_reasoning && <label className="written-reasoning">Written reasoning<textarea value={reasoning[question.id] || ''} onChange={(event) => onReasoning(question.id, event.target.value)} disabled={expired || deadlineUnavailable || submitting} required maxLength={5000} /></label>}</fieldset>)}</div> : <Empty title="Questions were not returned">Reload the contest list before continuing.</Empty>}
    {expired && <div className="contest-expired" role="status">The server deadline has passed. The server must confirm the final attempt status.{error && <button className="text-button" onClick={onExpireRetry} disabled={submitting}>Retry deadline check</button>}</div>}
    <div className="contest-attempt-actions"><button className="button button-quiet" onClick={onExit} disabled={submitting}>Leave attempt</button><button className="button button-primary" onClick={onSubmit} disabled={submitting || expired || deadlineUnavailable || !attempt.questions?.length || missingReasoning}>{submitting ? 'Submitting…' : 'Submit answers'} <span>↗</span></button></div>
  </section>
}

function AdminPaymentReviews({ payments, loading, error, onRetry, onReview, busyId }) {
  return   <section className="panel admin-contest-reviews" id="main-contest-payments">
    <div className="contest-section-heading"><div><div className="eyebrow">ADMIN ONLY</div><h2>Main contest payment review</h2><p>Review the submitted reference against payment evidence. Verification requires a confirmed transaction ID and an explicit access expiry.</p></div></div>
    {error && <ErrorState message={error} retry={onRetry} />}
    {loading ? <Loading label="Loading payment review queue…" /> : error ? null : payments.length === 0 ? <Empty title="No payment requests to review">The admin payment endpoint returned no requests.</Empty> : <div className="admin-contest-list">{payments.map((payment) => <AdminPaymentCard key={payment.id} payment={payment} busy={busyId === payment.id} onReview={onReview} />)}</div>}
  </section>
}

function AdminPaymentCard({ payment, busy, onReview }) {
  const [form, setForm] = useState({ decision: 'under_review', verification_notes: '', rejection_reason: '', confirmed_transaction_id: '', expires_at: '' })
  const reviewable = ['pending', 'under_review'].includes(payment.status)
  const submit = (event) => {
    event.preventDefault()
    onReview(payment.id, form)
  }
  return <article className="admin-contest-card">
    <div className="admin-contest-summary"><div><strong>{payment.full_name || payment.email || 'Account holder'}</strong><span>{payment.email} · {payment.phone_number}</span><span>{payment.field} · KES {payment.amount_kes} · Till {payment.till_number}</span><span>Submitted reference: <b>{payment.payment_reference || 'Not supplied'}</b></span><small>{formatDate(payment.created_at)}</small></div><span className={`contest-status status-${payment.status}`}>{payment.status?.replaceAll('_', ' ')}</span></div>
    {payment.verification_notes && <p className="admin-evidence">Review notes: {payment.verification_notes}</p>}
    {payment.rejection_reason && <p className="admin-evidence">Rejection reason: {payment.rejection_reason}</p>}
    {reviewable ? <form className="admin-review-form" onSubmit={submit}>
      <label>Decision<select value={form.decision} onChange={(event) => setForm({ ...form, decision: event.target.value })}><option value="under_review">Keep under review</option><option value="verified">Verify payment</option><option value="rejected">Reject payment</option></select></label>
      <label>Evidence / verification notes<textarea rows="2" value={form.verification_notes} onChange={(event) => setForm({ ...form, verification_notes: event.target.value })} required /></label>
      {form.decision === 'verified' && <><label>Confirmed transaction ID<input value={form.confirmed_transaction_id} onChange={(event) => setForm({ ...form, confirmed_transaction_id: event.target.value })} required /></label><label>Access expires at<input type="datetime-local" value={form.expires_at} onChange={(event) => setForm({ ...form, expires_at: event.target.value })} required /></label></>}
      {form.decision === 'rejected' && <label>Rejection reason<textarea rows="2" value={form.rejection_reason} onChange={(event) => setForm({ ...form, rejection_reason: event.target.value })} required /></label>}
      <button className="button button-primary" disabled={busy}>{busy ? 'Saving decision…' : 'Record decision'} <span>↗</span></button>
    </form> : <div className="admin-final-decision">Final status recorded{payment.expires_at ? ` · access expires ${formatDate(payment.expires_at)}` : ''}</div>}
  </article>
}
