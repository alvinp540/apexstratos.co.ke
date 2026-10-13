import { useState, useEffect } from 'react'
import Navbar from '../components/common/Navbar'
import CohortLeaderboard from '../components/cohorts/CohortLeaderboard'
import QuestionCard from '../components/cohorts/QuestionCard'
import AssessmentTimer from '../components/cohorts/AssessmentTimer'
import LoadingSpinner from '../components/common/LoadingSpinner'
import toast from 'react-hot-toast'
import { getCohorts, enrollCohort, getAssessments, startAssessment, submitAssessment, sendHeartbeat } from '../api/cohortAPI'
import { listPSPRegistrations, createPSPRegistration } from '../api/pspAPI'
import { Link } from 'react-router-dom'

const tierLabels = { '10kes': 'KES 10', '100kes': 'KES 100', '1000kes': 'KES 1,000' }

export default function CohortsPage() {
  const [cohorts, setCohorts] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedCohort, setSelectedCohort] = useState(null)
  const [assessments, setAssessments] = useState([])
  const [activeAttempt, setActiveAttempt] = useState(null)
  const [activeAssessment, setActiveAssessment] = useState(null)
  const [answers, setAnswers] = useState({})
  const [view, setView] = useState('list')
  const [pspRegistrations, setPspRegistrations] = useState([])
  const [tier, setTier] = useState('10kes')
  const [paymentDetails, setPaymentDetails] = useState({ full_name: '', phone_number: '' })
  const [videoWatchedSeconds, setVideoWatchedSeconds] = useState(0)
  const [videoCompleted, setVideoCompleted] = useState(false)

  useEffect(() => {
    Promise.all([
      getCohorts().then(({ data }) => setCohorts(data.results || data)),
      listPSPRegistrations().then(setPspRegistrations),
    ]).catch(() => {}).finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!activeAttempt) return
    const id = setInterval(() => {
      sendHeartbeat(activeAttempt.id, { tab_switch: false, time_anomaly: false, video_watched_seconds: videoWatchedSeconds, video_completed: videoCompleted }).catch(() => {})
    }, 30000)
    return () => clearInterval(id)
  }, [activeAttempt, videoWatchedSeconds, videoCompleted])

  useEffect(() => {
    if (!activeAttempt) return
    const onVisibilityChange = () => {
      if (document.hidden) {
        toast.error('Leaving the assessment tab is recorded as a cheating event.')
        sendHeartbeat(activeAttempt.id, { tab_switch: true, time_anomaly: false }).catch(() => {})
      }
    }
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => document.removeEventListener('visibilitychange', onVisibilityChange)
  }, [activeAttempt])

  const handleEnroll = async (cohortId) => {
    try {
      await enrollCohort(cohortId)
      toast.success('Enrolled!')
    } catch (err) {
      toast.error(err.response?.data?.error || 'Already enrolled or cohort full.')
    }
  }

  const handleRegister = async (cohortId) => {
    try {
      const registration = await createPSPRegistration({ ...paymentDetails, psp_tier: tier, cohort: cohortId })
      setPspRegistrations((current) => [registration, ...current])
      toast.success('Registration submitted. An admin will verify your payment.')
    } catch (err) {
      toast.error(Object.values(err.response?.data || {}).flat().join(' ') || 'Registration failed.')
    }
  }

  const handleSelectCohort = async (cohort) => {
    setSelectedCohort(cohort)
    const { data } = await getAssessments(cohort.id)
    setAssessments(data)
    setView('cohort')
  }

  const handleStartAssessment = async (assessment) => {
    try {
      const { data } = await startAssessment(assessment.id)
      setActiveAttempt(data)
      setActiveAssessment(assessment)
      setAnswers({})
      setVideoWatchedSeconds(0)
      setVideoCompleted(false)
      setView('assessment')
    } catch (err) {
      toast.error(err.response?.data?.error || 'Could not start assessment.')
    }
  }

  const handleSubmit = async () => {
    try {
      const { data } = await submitAssessment(activeAssessment.id, answers, { video_watched_seconds: videoWatchedSeconds, video_completed: videoCompleted })
      toast.success(`${data.message} Score: ${data.score?.toFixed(1)}%`)
      setView('cohort')
      setActiveAttempt(null)
    } catch (err) {
      toast.error(err.response?.data?.error || 'Submission failed.')
    }
  }

  if (loading) return <><Navbar /><LoadingSpinner /></>

  const demoAssessment = {
    title: 'Cohort Assessment',
    time_limit_minutes: 15,
    questions: [
      {
        id: 'q1',
        text: 'The API endpoint /user/123 is returning an error. What is the MOST likely cause?',
        points: 1,
        options: [
          { id: 'a', text: 'Database connection is failing.' },
          { id: 'b', text: 'The getUser function is not exported properly.' },
          { id: 'c', text: 'The route path is incorrect.' },
          { id: 'd', text: 'User ID is not being passed in the request.' },
        ],
      },
      {
        id: 'q2',
        text: 'Why is Option B the best solution?',
        points: 1,
        options: [
          { id: 'a', text: 'Because the function is not available outside the file.' },
          { id: 'b', text: 'Because it logs to console and improves debugging.' },
          { id: 'c', text: 'Because the database schema is not correct.' },
          { id: 'd', text: 'Because the request headers are missing authorization.' },
        ],
      },
    ],
  }

  return (
    <>
      <Navbar />
      <div className="page-container" style={{ maxWidth: '1280px' }}>
        {view === 'list' && (
          <>
            <div style={{ background: 'linear-gradient(135deg, rgba(34,197,94,0.12), rgba(139,92,246,0.12))', border: '1px solid rgba(148,163,184,0.12)', borderRadius: '1.2rem', padding: '1.2rem', marginBottom: '1.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                <div>
                  <div style={{ color: '#a78bfa', textTransform: 'uppercase', letterSpacing: '0.12em', fontSize: '0.7rem', fontWeight: 700 }}>Assessment</div>
                  <h2 style={{ marginTop: '0.3rem', fontSize: '2rem', fontWeight: 800 }}>Open Cohorts</h2>
                </div>
                <div style={{ background: 'rgba(15,23,42,0.8)', border: '1px solid rgba(148,163,184,0.12)', borderRadius: '999px', padding: '0.55rem 0.9rem', fontWeight: 700, color: '#e2e8f0' }}>Question 7 of 20</div>
              </div>
            </div>

            <div style={{ display: 'grid', gap: '1rem' }}>
              {cohorts.map((c) => (
                <div key={c.id} className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem', background: 'rgba(15,23,42,0.78)', border: '1px solid rgba(148,163,184,0.12)' }}>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: '1.1rem' }}>{c.title}</div>
                    <div style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>{c.profession} · {tierLabels[c.payment_tier]} · {c.participant_count}/{c.max_participants} placed · Unlocks at {c.assessment_unlock_threshold}</div>
                  </div>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <button onClick={() => handleEnroll(c.id)} className="btn-outline">Enroll</button>
                    <button onClick={() => handleSelectCohort(c)} className="btn-primary">View</button>
                  </div>
                </div>
              ))}
              {cohorts.length === 0 && <p style={{ color: 'var(--color-text-muted)' }}>No open cohorts at the moment.</p>}
            </div>
          </>
        )}

        {view === 'cohort' && selectedCohort && (
          <>
            <button onClick={() => setView('list')} style={{ marginBottom: '1rem', background: 'none', color: '#a78bfa', padding: 0, fontWeight: 700 }}>← Back</button>
            <h2 style={{ marginBottom: '0.5rem', fontSize: '2rem', fontWeight: 800 }}>{selectedCohort.title}</h2>
            <div className="card" style={{ marginBottom: '1rem' }}>
              <strong>Payment status</strong>
              <div style={{ marginTop: '0.45rem', color: 'var(--color-text-muted)' }}>
                Pay the selected tier to Till <strong style={{ color: 'var(--color-text)' }}>1598106</strong>. Keep the payment reference for admin verification.
              </div>
              {pspRegistrations.filter((r) => r.cohort === selectedCohort.id).map((r) => (
                <div key={r.id} style={{ marginTop: '0.4rem' }}>Tier {r.psp_tier}: <strong>{r.status}</strong>{r.status === 'failed' ? ' - payment was not clear.' : ''}</div>
              ))}
              {!pspRegistrations.some((r) => r.cohort === selectedCohort.id && ['pending', 'confirmed', 'active'].includes(r.status)) && (
                <div style={{ display: 'grid', gap: '0.5rem', marginTop: '0.7rem' }}>
                  <input placeholder="Full name" value={paymentDetails.full_name} onChange={(e) => setPaymentDetails({ ...paymentDetails, full_name: e.target.value })} />
                  <input placeholder="Phone number" value={paymentDetails.phone_number} onChange={(e) => setPaymentDetails({ ...paymentDetails, phone_number: e.target.value })} />
                  <select value={tier} onChange={(e) => setTier(e.target.value)}><option value="10kes">KES 10</option><option value="100kes">KES 100</option><option value="1000kes">KES 1,000</option></select>
                  <button onClick={() => handleRegister(selectedCohort.id)} className="btn-primary">Submit payment for verification</button>
                </div>
              )}
            </div>
            <div className="card" style={{ marginBottom: '1rem', display: 'flex', gap: '0.6rem', flexWrap: 'wrap', alignItems: 'center' }}>
              <strong>Capability pathway</strong>
              <span style={{ color: 'var(--color-text-muted)' }}>Performance</span><span>→</span>
              <Link to="/mentors">Mentorship</Link><span>→</span>
              <Link to="/rankings">Leaderboard & merit</Link><span>→</span>
              <Link to="/opportunities">Opportunity placement</Link>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem' }}>
              <div>
                <h3 style={{ marginBottom: '1rem' }}>Assessments</h3>
                {assessments.map((a) => (
                  <div key={a.title} className="card" style={{ marginBottom: '0.75rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(15,23,42,0.78)', border: '1px solid rgba(148,163,184,0.12)' }}>
                    <div>
                      <div style={{ fontWeight: 600 }}>{a.title}</div>
                      <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>{a.difficulty || 'Intermediate'} · {a.time_limit_minutes || 15}min · Pass: {a.passing_score || 75}%</div>
                    </div>
                    <button onClick={() => handleStartAssessment(a)} className="btn-primary">Start</button>
                  </div>
                ))}
              </div>
              <div>
                <h3 style={{ marginBottom: '1rem' }}>Leaderboard</h3>
                <CohortLeaderboard cohortId={selectedCohort.id} />
              </div>
            </div>
          </>
        )}

        {view === 'assessment' && activeAssessment && (
          <div onCopy={(e) => e.preventDefault()} onContextMenu={(e) => e.preventDefault()} style={{ userSelect: 'none' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.2rem', gap: '1rem', flexWrap: 'wrap' }}>
              <div>
                <div style={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.14em', color: '#a78bfa', fontWeight: 700 }}>Question 7 of 20</div>
                <h2 style={{ marginTop: '0.25rem', fontSize: '2rem', fontWeight: 800 }}>{activeAssessment.title}</h2>
              </div>
              <AssessmentTimer limitMinutes={activeAssessment.time_limit_minutes} startedAt={activeAttempt.started_at} onExpire={handleSubmit} />
            </div>

            <div style={{ background: 'rgba(15,23,42,0.82)', border: '1px solid rgba(148,163,184,0.12)', borderRadius: '1rem', padding: '1.3rem', marginBottom: '1rem' }}>
              <div style={{ fontSize: '0.76rem', color: '#a78bfa', textTransform: 'uppercase', letterSpacing: '0.12em', fontWeight: 700 }}>Scenario video</div>
              <video controls controlsList="nodownload" src={activeAssessment.video_url} onTimeUpdate={(e) => setVideoWatchedSeconds(Math.floor(e.currentTarget.currentTime))} onEnded={() => setVideoCompleted(true)} style={{ width: '100%', maxHeight: '420px', borderRadius: '0.9rem', marginTop: '0.7rem' }} />
              <p style={{ color: 'var(--color-warning)', marginTop: '0.6rem' }}>Stay in a quiet place. Tab switches, unusual timing, and copied answers are recorded and may result in a zero score.</p>
            </div>

            {(activeAttempt.question_order || []).map((questionId, index) => activeAssessment.questions.find((q) => String(q.id) === questionId)).filter(Boolean).map((q, index) => (
              <QuestionCard key={q.id || index} question={q} index={index} selected={answers[q.id || index]} onSelect={(qId, val) => setAnswers((prev) => ({ ...prev, [qId]: val }))} />
            ))}

            <button onClick={handleSubmit} disabled={!videoCompleted} className="btn-primary" style={{ marginTop: '1rem', width: '100%' }}>{videoCompleted ? 'Submit Assessment' : 'Finish watching the video to submit'}</button>
          </div>
        )}
      </div>
    </>
  )
}
