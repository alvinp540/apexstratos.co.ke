import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import api, { getErrorMessage, unwrapList } from '../api/client'
import { studyAreas } from '../data'
import Page from '../components/Page'
import { Empty, ErrorState, Loading, PaginationControls } from '../components/States'
import WeeklyScheduleNotice from '../components/WeeklyScheduleNotice'
import SupportApplicationFields from '../components/SupportApplicationFields'
import { useAuth } from '../context/AuthContext'
import {
  applyForSupportProgram,
  decideSupportApplication,
  getAdminSupportApplications,
  getSupportApplications,
  getSupportPrograms,
  submitSupportApplicationInformation,
} from '../api/cohortAPI'

export function StudyAreas() {
  return <Page eyebrow="LEARN AT YOUR PACE" title="Choose a discipline" description="Explore an area to see published tutorials currently available from Apex.">
    <div className="discipline-grid study-grid">{studyAreas.map((area, index) => <Link key={area} to={`/study/${encodeURIComponent(area)}`} className="discipline-card"><span className="card-index">{String(index + 1).padStart(2, '0')}</span><strong>{area}</strong><span className="card-arrow">↗</span></Link>)}</div>
    <div className="info-note"><span>i</span><p>Tutorial availability depends on what has been published on the platform. Areas without published lessons will say so here.</p></div>
  </Page>
}

export function Tutorials() {
  const [params, setParams] = useState({ field: '', month: '', week: '', topic: '' })
  const [page, setPage] = useState(1)
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [status, setStatus] = useState({ loading: true, error: '' })
  const load = useCallback(async () => {
    setStatus({ loading: true, error: '' })
    try {
      const query = Object.fromEntries(Object.entries({ ...params, page }).filter(([, value]) => value))
      const { data } = await api.get('/cohorts/tutorials/', { params: query })
      setItems(unwrapList(data))
      setTotal(data?.count ?? unwrapList(data).length)
    } catch (error) {
      setStatus({ loading: false, error: getErrorMessage(error) })
      return
    }
    setStatus({ loading: false, error: '' })
  }, [page, params])
  useEffect(() => { load() }, [load])
  const update = (event) => {
    setParams({ ...params, [event.target.name]: event.target.value })
    setPage(1)
  }
  return <Page eyebrow="LEARNING LIBRARY" title="Tutorial Library" description="Free written lessons and ten-question assessments, organized by study area and week.">
    <WeeklyScheduleNotice activity="tutorials" />
    <div className="library-summary"><strong>Free</strong><span>{total} matching published assessments · initial target 640 assessments / 6,400 questions</span></div>
    <div className="filter-row"><label>Study area<select name="field" value={params.field} onChange={update}><option value="">All areas</option>{studyAreas.map((area) => <option key={area}>{area}</option>)}</select></label><label>Week<select name="week" value={params.week} onChange={update}><option value="">All 8 weeks</option>{Array.from({ length: 8 }, (_, index) => <option key={index + 1} value={index + 1}>Week {index + 1}</option>)}</select></label><label>Topic<input name="topic" maxLength={120} value={params.topic} onChange={update} placeholder="Search titles and descriptions" /></label></div>
    {status.loading ? <Loading label="Finding published tutorials…" /> : status.error ? <ErrorState message={status.error} retry={load} /> : items.length === 0 ? <Empty title="No published tutorial assessments match these filters">The database currently has no published tutorial assessments for this selection.</Empty> : <><div className="content-grid">{items.map((tutorial) => <TutorialCard key={tutorial.id} tutorial={tutorial} />)}</div><PaginationControls page={page} total={total} onPageChange={setPage} /></>}
  </Page>
}

export function AreaTutorials() {
  const { area } = useParams()
  const field = decodeURIComponent(area || '')
  const [items, setItems] = useState([])
  const [week, setWeek] = useState('')
  const [topic, setTopic] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [status, setStatus] = useState({ loading: true, error: '' })
  const load = useCallback(async () => {
    setStatus({ loading: true, error: '' })
    try {
      const { data } = await api.get('/cohorts/tutorials/', { params: { field, page, ...(week ? { week } : {}), ...(topic ? { topic } : {}) } })
      setItems(unwrapList(data))
      setTotal(data?.count ?? unwrapList(data).length)
      setStatus({ loading: false, error: '' })
    } catch (error) { setStatus({ loading: false, error: getErrorMessage(error) }) }
  }, [field, page, topic, week])
  useEffect(() => { load() }, [load])
  return <Page eyebrow="STUDY AREA" title={field} description="Published lessons available for this discipline.">
    <WeeklyScheduleNotice activity="tutorials" />
    <Link className="back-link inline-back" to="/study">← All study areas</Link>
    <div className="filter-row"><label>Week<select value={week} onChange={(event) => { setWeek(event.target.value); setPage(1) }}><option value="">All 8 weeks</option>{Array.from({ length: 8 }, (_, index) => <option key={index + 1} value={index + 1}>Week {index + 1}</option>)}</select></label><label>Topic<input maxLength={120} value={topic} onChange={(event) => { setTopic(event.target.value); setPage(1) }} placeholder="Search titles and descriptions" /></label></div>
    {status.loading ? <Loading label={`Loading ${field} tutorials…`} /> : status.error ? <ErrorState message={status.error} retry={load} /> : !items.length ? <Empty title="No published tutorial assessments match this selection">The database currently has no published tutorial assessments for {field}.</Empty> : <><div className="content-grid">{items.map((tutorial) => <TutorialCard key={tutorial.id} tutorial={tutorial} />)}</div><PaginationControls page={page} total={total} onPageChange={setPage} /></>}
  </Page>
}

function TutorialCard({ tutorial }) {
  return <Link to={`/tutorials/${tutorial.id}`} className="tutorial-card"><div className="tutorial-card-top"><span className="tag">{tutorial.field}</span><span className="card-arrow">↗</span></div><h2>{tutorial.title}</h2><p>{tutorial.description}</p><div className="tutorial-meta"><span>Week {tutorial.week}</span><span>{tutorial.progress?.completed ? `Completed · best ${tutorial.progress.best_score}%` : `${tutorial.questions?.length || 10} questions · Free`}</span></div></Link>
}

export function TutorialDetail() {
  const { id } = useParams()
  const [item, setItem] = useState(null)
  const [status, setStatus] = useState({ loading: true, error: '' })
  const load = useCallback(() => {
    setStatus({ loading: true, error: '' })
    api.get(`/cohorts/tutorials/${id}/`).then(({ data }) => { setItem(data); setStatus({ loading: false, error: '' }) }).catch((error) => setStatus({ loading: false, error: getErrorMessage(error) }))
  }, [id])
  useEffect(() => { load() }, [load])
  if (status.loading) return <Page eyebrow="TUTORIAL" title="Loading lesson"><Loading /></Page>
  if (status.error) return <Page eyebrow="TUTORIAL" title="Lesson unavailable"><ErrorState message={status.error} retry={load} /></Page>
  if (!item) return <Page eyebrow="TUTORIAL" title="Lesson unavailable"><Empty /></Page>
  const sections = [
    ['Concept', item.concept_explanation], ['Terminology & components', item.terminology_and_components],
    ['Why it matters', item.why_it_matters], ['How it works', item.how_it_works],
    ['Worked examples', item.worked_examples], ['Common mistakes', item.common_mistakes],
    ['Practical application', item.practical_application], ['Decisions & tradeoffs', item.decisions_and_tradeoffs],
    ['Related concepts', item.related_concepts],
  ].filter(([, value]) => value)
  return <Page eyebrow={item.field} title={item.title} description={item.description}>
    <Link className="back-link inline-back" to={`/study/${encodeURIComponent(item.field)}`}>← Back to {item.field}</Link>
    <div className="lesson-meta"><span className="tag">{item.difficulty}</span><span>Week {item.week}</span><span>Free · 10 questions</span>{item.progress?.completed && <span>Completed · best score {item.progress.best_score}%</span>}</div>
    {item.learning_objectives?.length > 0 && <section className="lesson-section"><div className="eyebrow">LEARNING OBJECTIVES</div><ul>{item.learning_objectives.map((objective, index) => <li key={`${index}-${objective}`}>{objective}</li>)}</ul></section>}
    {sections.length > 0 && <div className="lesson-sections">{sections.map(([heading, content]) => <section className="lesson-section" key={heading}><h2>{heading}</h2><p>{content}</p></section>)}</div>}
    <WeeklyScheduleNotice activity="tutorials" />
    <TutorialAssessment tutorial={item} onComplete={load} />
  </Page>
}

function TutorialAssessment({ tutorial, onComplete }) {
  const [attempt, setAttempt] = useState(tutorial.current_attempt || null)
  const [answers, setAnswers] = useState(tutorial.current_attempt?.answers || {})
  const [reasoning, setReasoning] = useState(tutorial.current_attempt?.reasoning || {})
  const [remaining, setRemaining] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (tutorial.current_attempt?.id && tutorial.current_attempt.id !== attempt?.id) {
      setAttempt(tutorial.current_attempt)
      setAnswers(tutorial.current_attempt.answers || {})
      setReasoning(tutorial.current_attempt.reasoning || {})
    }
  }, [tutorial.current_attempt, attempt?.id])

  useEffect(() => {
    if (!attempt?.deadline_at || !attempt?.server_time || attempt.status !== 'in_progress') {
      setRemaining(null)
      return undefined
    }
    const deadline = Date.parse(attempt.deadline_at)
    const offset = Date.parse(attempt.server_time) - Date.now()
    if (!Number.isFinite(deadline) || !Number.isFinite(offset)) return undefined
    const update = () => setRemaining(Math.max(0, Math.ceil((deadline - (Date.now() + offset)) / 1000)))
    update()
    const timer = window.setInterval(update, 1000)
    return () => window.clearInterval(timer)
  }, [attempt?.id, attempt?.deadline_at, attempt?.server_time, attempt?.status])

  useEffect(() => {
    if (attempt?.status !== 'in_progress') return undefined
    const timer = window.setTimeout(() => {
      api.post(`/cohorts/tutorial-attempts/${attempt.id}/answers/`, { answers, reasoning })
        .catch((requestError) => {
          if (![409, 410].includes(requestError.response?.status)) setError(getErrorMessage(requestError))
        })
    }, 500)
    return () => window.clearTimeout(timer)
  }, [attempt?.id, attempt?.status, answers, reasoning])

  const start = async () => {
    setBusy(true)
    setError('')
    try {
      const { data } = await api.post(`/cohorts/tutorials/${tutorial.id}/attempts/`)
      setAttempt(data)
      setAnswers(data.answers || {})
      setReasoning(data.reasoning || {})
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setBusy(false)
    }
  }

  const submit = async () => {
    setBusy(true)
    setError('')
    try {
      const { data } = await api.post(`/cohorts/tutorial-attempts/${attempt.id}/submit/`, { answers, reasoning })
      setAttempt(data)
      onComplete()
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setBusy(false)
    }
  }

  if (!attempt) return <section className="lesson-section"><div className="eyebrow">ASSESSMENT</div><h2>Check your understanding</h2><p>Complete the ten-question assessment to save your progress. One attempt is allowed; refresh or reconnect to resume an active attempt.</p><button className="button button-primary" onClick={start} disabled={busy || !tutorial.can_start}>{busy ? 'Opening assessment…' : tutorial.can_start ? 'Start assessment' : 'Opens Monday–Thursday'}</button>{error && <p role="alert">{error}</p>}</section>
  const complete = attempt.questions.length === 10 && attempt.questions.every((question) =>
    answers[question.id] && (!question.requires_reasoning || reasoning[question.id]?.trim()),
  )
  return <section className="lesson-section"><div className="eyebrow">ASSESSMENT · {attempt.status === 'graded' ? `SCORE ${attempt.score}%` : attempt.status === 'timed_out' ? 'TIME EXPIRED' : '10 QUESTIONS'}</div><h2>{attempt.status === 'graded' ? 'Assessment results' : attempt.status === 'timed_out' ? 'Attempt expired' : 'Choose the best answer'}</h2>
    {attempt.status === 'in_progress' && <p role="timer">Time remaining: {remaining === null ? '—' : `${String(Math.floor(remaining / 60)).padStart(2, '0')}:${String(remaining % 60).padStart(2, '0')}`} · deadline is enforced by the server.</p>}
    {attempt.questions.map((question) => <fieldset className="tutorial-question" key={question.id}><legend>{question.order}. {question.prompt}</legend>{question.options.map((option) => <label key={option}><input type="radio" name={question.id} value={option} checked={answers[question.id] === option} disabled={attempt.status === 'graded'} onChange={() => setAnswers((current) => ({ ...current, [question.id]: option }))} />{option}</label>)}{question.requires_reasoning && <label className="written-reasoning">Written reasoning<textarea value={reasoning[question.id] || ''} onChange={(event) => setReasoning((current) => ({ ...current, [question.id]: event.target.value }))} disabled={attempt.status === 'graded'} required maxLength={5000} /></label>}{question.rationale && <p>{question.rationale}</p>}{question.written_reasoning && <p>Your reasoning: {question.written_reasoning}</p>}</fieldset>)}
    {attempt.status === 'in_progress' && <button className="button button-primary" onClick={submit} disabled={busy || !complete || remaining === 0}>{busy ? 'Submitting…' : 'Submit answers'}</button>}
    {error && <p role="alert">{error}</p>}
  </section>
}

export function Mentorship() {
  const [mentors, setMentors] = useState([])
  const [organizations, setOrganizations] = useState([])
  const [status, setStatus] = useState({ loading: true, error: '' })
  const load = async () => {
    setStatus({ loading: true, error: '' })
    try {
      const [mentorResult, orgResult] = await Promise.all([api.get('/profiles/mentors/'), api.get('/profiles/mentors/organizations/')])
      setMentors(unwrapList(mentorResult.data))
      setOrganizations(unwrapList(orgResult.data))
      setStatus({ loading: false, error: '' })
    } catch (error) { setStatus({ loading: false, error: getErrorMessage(error) }) }
  }
  useEffect(() => { load() }, [])
  return <Page eyebrow="PEOPLE & EXPERIENCE" title="Mentorship" description="Explore the mentors and organizations currently listed on Apex.">
    {status.loading ? <Loading label="Loading mentors…" /> : status.error ? <ErrorState message={status.error} retry={load} /> : mentors.length === 0 && organizations.length === 0 ? <Empty title="No mentors listed yet">There are no mentor profiles published on the platform right now.</Empty> : <>
      {organizations.length > 0 && <div className="organization-list">{organizations.map((org) => <article className="organization-card" key={org.id}><span className="eyebrow">ORGANIZATION</span><h2>{org.name}</h2><p>{org.description || 'No description provided.'}</p></article>)}</div>}
      <div className="content-grid">{mentors.map((mentor) => <article key={mentor.id} className="mentor-card"><div className="mentor-avatar">{(mentor.user?.username || 'M')[0].toUpperCase()}</div><div><h2>{mentor.user?.username || 'Mentor'}</h2><p>{mentor.organization?.name || 'Independent mentor'}</p></div><p className="mentor-bio">{mentor.bio || 'No mentor biography provided.'}</p><div className="tag-row">{(mentor.skills || []).map((skill) => <span className="tag" key={skill}>{skill}</span>)}</div><div className="mentor-meta"><span>{mentor.tier || 'Mentor'}</span><span>Consistency: {mentor.consistency_score ?? '—'}</span></div></article>)}</div>
    </>}
  </Page>
}

export function Opportunities() {
  const { user } = useAuth()
  const [jobs, setJobs] = useState([])
  const [status, setStatus] = useState({ loading: true, error: '' })
  const [programs, setPrograms] = useState([])
  const [applications, setApplications] = useState([])
  const [adminApplications, setAdminApplications] = useState([])
  const [supportStatus, setSupportStatus] = useState({ loading: true, error: '' })
  const [adminError, setAdminError] = useState('')
  const [forms, setForms] = useState({})
  const [informationForms, setInformationForms] = useState({})
  const [busyId, setBusyId] = useState('')
  const [formError, setFormError] = useState('')
  const loadJobs = useCallback(() => {
    setStatus({ loading: true, error: '' })
    api.get('/vendor/opportunities/').then(({ data }) => { setJobs(unwrapList(data)); setStatus({ loading: false, error: '' }) }).catch((error) => setStatus({ loading: false, error: getErrorMessage(error) }))
  }, [])
  const loadSupport = useCallback(async () => {
    setSupportStatus({ loading: true, error: '' })
    try {
      const [programResult, applicationResult] = await Promise.all([
        getSupportPrograms(),
        getSupportApplications(),
      ])
      setPrograms(unwrapList(programResult.data))
      setApplications(unwrapList(applicationResult.data))
      setSupportStatus({ loading: false, error: '' })
    } catch (error) {
      setSupportStatus({ loading: false, error: getErrorMessage(error) })
    }
    if (user?.is_admin) {
      try {
        const { data } = await getAdminSupportApplications()
        setAdminApplications(unwrapList(data))
        setAdminError('')
      } catch (error) {
        setAdminError(getErrorMessage(error))
      }
    }
  }, [user?.is_admin])
  useEffect(() => { loadJobs(); loadSupport() }, [loadJobs, loadSupport])

  const updateForm = (programId, key, value) => {
    setForms((current) => ({
      ...current,
      [programId]: { ...current[programId], [key]: value },
    }))
  }
  const submitApplication = async (event, program) => {
    event.preventDefault()
    setBusyId(program.id)
    setFormError('')
    try {
      const form = forms[program.id] || {}
      await applyForSupportProgram(program.id, {
        full_name: form.full_name || '',
        registered_phone_number: form.registered_phone_number || '',
        mpesa_number: form.mpesa_number || '',
        application_data: form.application_data || {},
      })
      setForms((current) => ({ ...current, [program.id]: {} }))
      await loadSupport()
    } catch (error) {
      setFormError(getErrorMessage(error))
    } finally {
      setBusyId('')
    }
  }
  const reviewApplication = async (applicationId, payload) => {
    setBusyId(applicationId)
    setAdminError('')
    try {
      await decideSupportApplication(applicationId, payload)
      await loadSupport()
    } catch (error) {
      setAdminError(getErrorMessage(error))
    } finally {
      setBusyId('')
    }
  }
  const submitRequestedInformation = async (event, application) => {
    event.preventDefault()
    setBusyId(application.id)
    setFormError('')
    try {
      const values = informationForms[application.id] || {}
      await submitSupportApplicationInformation(application.id, {
        mpesa_number: values.mpesa_number || application.mpesa_number,
        application_data: values.application_data || application.application_data || {},
      })
      await loadSupport()
    } catch (error) {
      setFormError(getErrorMessage(error))
    } finally {
      setBusyId('')
    }
  }

  return <Page eyebrow="NEXT STEPS" title="Eligible Opportunities & Support" description="Review published programme rules, apply when eligible, and track every review and payment status. Eligibility does not guarantee funding or payout.">
    <section className="support-programme-section">
      <div className="contest-section-heading"><div><div className="eyebrow">MERIT-BASED SUPPORT</div><h2>Eligible Opportunities & Support</h2><p>Each programme publishes its own merit cutoff and funding status. Eligibility uses completed, unflagged Main Contest assessment averages; tutorial consistency is recorded as a tie-break factor.</p></div><button className="button button-quiet" onClick={loadSupport}>↻ Refresh</button></div>
      {supportStatus.loading ? <Loading label="Checking published programmes and eligibility…" /> : supportStatus.error ? <ErrorState message={supportStatus.error} retry={loadSupport} /> : programs.length === 0 ? <Empty title="No published support programmes">No opportunity, reward, sponsorship, or payout programme is currently published.</Empty> : <div className="support-programme-list">{programs.map((program) => {
        const application = program.application || applications.find((item) => item.program === program.id)
        const form = forms[program.id] || {}
        return <article className="support-programme-card" key={program.id}>
          <div className="tutorial-card-top"><span className="tag">{program.program_type.replaceAll('_', ' ')}</span><span className={`contest-status status-${application?.status || (program.eligible ? 'eligible' : 'pending')}`}>{application?.status?.replaceAll('_', ' ') || (program.eligible ? 'Eligible to apply' : 'Not yet eligible')}</span></div>
          <h3>{program.title}</h3><p>{program.description}</p>
          <div className="support-programme-facts"><span>Published criterion: {program.metric_label ? `${program.metric_label} ≥ ${program.merit_cutoff}` : 'Eligibility rules need administrator configuration'}</span><span>{program.metric_label || 'Verified result'}: {program.merit_score} ({program.completed_requirements} qualifying records)</span><span>Tutorial consistency: {program.tutorial_consistency_weeks} of 8 weeks</span><span>Funding: {program.funding_status.replaceAll('_', ' ')}</span>{program.deadline && <span>Deadline: {new Date(program.deadline).toLocaleString()}</span>}</div>
          <p className="support-eligibility-rules"><strong>Eligibility rules:</strong> {program.eligibility_rules}</p>
          {application ? <div className="support-application-status"><strong>Application status: {application.status.replaceAll('_', ' ')}</strong>{application.admin_reason && <p>{application.admin_reason}</p>}{application.payment_reference && <p>Payment reference: {application.payment_reference}</p>}{application.payment_confirmed_at && <p>Payment confirmed: {new Date(application.payment_confirmed_at).toLocaleString()}</p>}</div> : program.eligible && program.funding_status !== 'closed' ? <form className="support-application-form" onSubmit={(event) => submitApplication(event, program)}>
            <h4>Application and payment details</h4><p>Submitting an application requests review; it does not guarantee selection, funding, or payment.</p>
            <label>Registered full name<input required maxLength={200} autoComplete="name" value={form.full_name ?? user?.full_name ?? ''} onChange={(event) => updateForm(program.id, 'full_name', event.target.value)} /></label>
            <label>Registered phone number<input required maxLength={20} autoComplete="tel" value={form.registered_phone_number ?? user?.phone_number ?? ''} onChange={(event) => updateForm(program.id, 'registered_phone_number', event.target.value)} /></label>
            <label>M-Pesa number for this programme<input required maxLength={20} autoComplete="tel" value={form.mpesa_number || ''} onChange={(event) => updateForm(program.id, 'mpesa_number', event.target.value)} /></label>
            <SupportApplicationFields
              fields={program.application_fields}
              values={form.application_data || {}}
              onChange={(key, value) => updateForm(program.id, 'application_data', {
                ...form.application_data,
                [key]: value,
              })}
            />
            {formError && <div className="alert alert-error" role="alert">{formError}</div>}
            <button className="button button-primary" type="submit" disabled={busyId === program.id}>{busyId === program.id ? 'Submitting…' : 'Submit application'}</button>
          </form> : <p className="support-not-eligible">{program.eligibility_reason || 'Not currently eligible under the published programme rules.'}</p>}
        </article>
      })}</div>}
    </section>
    <section className="support-applications-section"><div className="eyebrow">YOUR RECORDS</div><h2>Applications & payment status</h2>{applications.length ? <div className="support-application-list">{applications.map((application) => {
      const values = informationForms[application.id] || {}
      return <article className="support-application-status" key={application.id}><strong>{application.program_title}</strong><span>{application.status.replaceAll('_', ' ')}</span><small>Submitted {new Date(application.submitted_at).toLocaleString()}</small>{application.admin_reason && <p>{application.admin_reason}</p>}{application.application_fields_at_application?.map((field) => application.application_data?.[field.key] && <p key={field.key}><strong>{field.label}:</strong> {application.application_data[field.key]}</p>)}{application.payment_reference && <p>Payment reference: {application.payment_reference}</p>}{application.status === 'paid' && application.payment_confirmed_at && <p>Payment confirmed: {new Date(application.payment_confirmed_at).toLocaleString()}</p>}{application.status === 'awaiting_information' && <form className="support-application-form" onSubmit={(event) => submitRequestedInformation(event, application)}><label>Updated M-Pesa number<input required maxLength={20} autoComplete="tel" value={values.mpesa_number ?? application.mpesa_number} onChange={(event) => setInformationForms((current) => ({ ...current, [application.id]: { ...current[application.id], mpesa_number: event.target.value } }))} /></label><SupportApplicationFields fields={application.application_fields_at_application} values={values.application_data ?? application.application_data ?? {}} onChange={(key, value) => setInformationForms((current) => ({ ...current, [application.id]: { ...current[application.id], application_data: { ...current[application.id]?.application_data, [key]: value } } }))} />{formError && <div className="alert alert-error" role="alert">{formError}</div>}<button className="button button-primary" disabled={busyId === application.id}>{busyId === application.id ? 'Submitting…' : 'Submit requested information'}</button></form>}</article>
    } )}</div> : <Empty title="No applications submitted">Eligible forms appear with published programmes above. Your application history will be kept here.</Empty>}</section>
    {user?.is_admin && <AdminSupportApplications applications={adminApplications} error={adminError} busyId={busyId} onReview={reviewApplication} onRetry={loadSupport} />}
    <section className="support-vendor-opportunities"><div className="eyebrow">SEPARATE PAID-WORK FEATURE</div><h2>Vendor-listed work</h2><p>These vendor job listings are separate from merit awards, philanthropic support, sponsored access, and programme payouts.</p>
      {status.loading ? <Loading label="Loading vendor work…" /> : status.error ? <ErrorState message={status.error} retry={loadJobs} /> : jobs.length === 0 ? <Empty title="No vendor work listed">There are no vendor job listings available to this account right now.</Empty> : <div className="content-grid">{jobs.map((job) => <article key={job.id} className="opportunity-card"><div className="tutorial-card-top"><span className="tag">{job.profession_required}</span><span className="job-status">{job.status}</span></div><h2>{job.title}</h2><p>{job.description}</p><div className="budget">{job.currency || 'KES'} {job.budget_min ?? '—'} – {job.budget_max ?? '—'}</div><div className="tag-row">{(job.skills_required || []).map((skill) => <span key={skill} className="tag">{skill}</span>)}</div><div className="job-details"><span>Minimum merit: {job.min_trust_score ?? 0}</span><span>{job.deadline ? `Deadline ${new Date(job.deadline).toLocaleDateString()}` : 'No deadline listed'}</span></div></article>)}</div>}
    </section>
  </Page>
}

function AdminSupportApplications({ applications, error, busyId, onReview, onRetry }) {
  return <section className="panel admin-support-applications"><div className="contest-section-heading"><div><div className="eyebrow">ADMIN ONLY · PRIVATE DETAILS</div><h2>Support application review</h2><p>Verify applicant details, record a decision and reason, and confirm payment with a unique reference.</p></div><button className="button button-quiet" onClick={onRetry}>↻ Refresh</button></div>
    {error && <ErrorState message={error} retry={onRetry} />}
    {!error && applications.length === 0 ? <Empty title="No support applications submitted">Eligible applications appear here after submission.</Empty> : <div className="admin-support-list">{applications.map((application) => <SupportApplicationReview key={application.id} application={application} busy={busyId === application.id} onReview={onReview} />)}</div>}
  </section>
}

const supportTransitions = {
  submitted: ['under_review', 'awaiting_information', 'declined'],
  under_review: ['approved', 'awaiting_funding', 'awaiting_information', 'declined'],
  approved: ['awaiting_funding', 'payment_processing', 'declined'],
  awaiting_funding: ['payment_processing', 'declined'],
  payment_processing: ['paid', 'declined'],
  awaiting_information: ['under_review', 'declined'],
}

function SupportApplicationReview({ application, busy, onReview }) {
  const [form, setForm] = useState({ status: application.status, admin_reason: application.admin_reason || '', payment_reference: application.payment_reference || '' })
  const submit = (event) => {
    event.preventDefault()
    onReview(application.id, form)
  }
  return <article className="admin-support-card"><div className="admin-support-summary"><div><strong>{application.program_title} · {application.full_name}</strong><span>Registered phone: {application.registered_phone_number} · M-Pesa: {application.mpesa_number}</span><small>Verified eligibility metric {application.merit_score_at_application} · tutorial consistency {application.tutorial_consistency_weeks_at_application}/8 · {application.status.replaceAll('_', ' ')}</small>{application.application_fields_at_application?.map((field) => application.application_data?.[field.key] && <p key={field.key}><strong>{field.label}:</strong> {application.application_data[field.key]}</p>)}</div></div>
    <form className="admin-review-form" onSubmit={submit}><label>Decision<select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}><option value={application.status}>{application.status.replaceAll('_', ' ')}</option>{(supportTransitions[application.status] || []).map((nextStatus) => <option key={nextStatus} value={nextStatus}>{nextStatus.replaceAll('_', ' ')}</option>)}</select></label>
      <label>Payment reference<input value={form.payment_reference} onChange={(event) => setForm({ ...form, payment_reference: event.target.value })} /></label>
      <label>Decision reason<textarea value={form.admin_reason} onChange={(event) => setForm({ ...form, admin_reason: event.target.value })} required={form.status === 'declined'} /></label>
      <button className="button button-primary" type="submit" disabled={busy || !supportTransitions[application.status]?.includes(form.status) && form.status !== application.status}>{busy ? 'Saving…' : 'Save review'}</button>
    </form>
  </article>
}

export function SponsoredView() {
  const { user } = useAuth()
  const [filters, setFilters] = useState({ field: '', week: '', topic: '' })
  const [assessments, setAssessments] = useState([])
  const [payments, setPayments] = useState([])
  const [adminPayments, setAdminPayments] = useState([])
  const [paymentReferences, setPaymentReferences] = useState({})
  const [transactionIds, setTransactionIds] = useState({})
  const [rejectionReasons, setRejectionReasons] = useState({})
  const [attempt, setAttempt] = useState(null)
  const [answers, setAnswers] = useState({})
  const [reasoning, setReasoning] = useState({})
  const [remaining, setRemaining] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [adminError, setAdminError] = useState('')
  const [status, setStatus] = useState({ loading: true, error: '' })
  const isAdmin = user?.role === 'admin' || user?.is_admin

  const load = useCallback(async () => {
    setStatus({ loading: true, error: '' })
    try {
      const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value))
      const [{ data }, paymentResponse] = await Promise.all([
        api.get('/cohorts/sponsored-view/assessments/', { params }),
        api.get('/cohorts/sponsored-view/payments/'),
      ])
      setAssessments(data.results || [])
      setPayments(unwrapList(paymentResponse.data))
      if (isAdmin) {
        try {
          const { data: adminData } = await api.get('/cohorts/admin/sponsored-view/payments/')
          setAdminPayments(unwrapList(adminData))
          setAdminError('')
        } catch (requestError) {
          setAdminError(getErrorMessage(requestError))
        }
      }
      setStatus({ loading: false, error: '' })
    } catch (requestError) {
      setStatus({ loading: false, error: getErrorMessage(requestError) })
    }
  }, [filters, isAdmin])
  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!attempt?.deadline_at || !attempt?.server_time || attempt.status !== 'in_progress') {
      setRemaining(null)
      return undefined
    }
    const deadline = Date.parse(attempt.deadline_at)
    const offset = Date.parse(attempt.server_time) - Date.now()
    if (!Number.isFinite(deadline) || !Number.isFinite(offset)) return undefined
    const update = () => setRemaining(Math.max(0, Math.ceil((deadline - (Date.now() + offset)) / 1000)))
    update()
    const timer = window.setInterval(update, 1000)
    return () => window.clearInterval(timer)
  }, [attempt?.id, attempt?.deadline_at, attempt?.server_time, attempt?.status])

  useEffect(() => {
    if (!attempt?.id || attempt.status !== 'in_progress') return undefined
    const timer = window.setTimeout(() => {
      api.post(`/cohorts/sponsored-view/attempts/${attempt.id}/answers/`, { answers, reasoning })
        .catch((requestError) => {
          if (![409, 410].includes(requestError.response?.status)) setError(getErrorMessage(requestError))
        })
    }, 500)
    return () => window.clearTimeout(timer)
  }, [attempt?.id, attempt?.status, answers, reasoning])

  const beginAttempt = async (paymentId) => {
    setBusy(true)
    setError('')
    try {
      const { data } = await api.post(`/cohorts/sponsored-view/payments/${paymentId}/start/`)
      setAttempt(data)
      setAnswers(data.answers || {})
      setReasoning(data.reasoning || {})
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setBusy(false)
    }
  }

  const requestPayment = async (assessment) => {
    const reference = (paymentReferences[assessment.id] || '').trim()
    if (!reference) {
      setError('Enter the M-Pesa reference for your KSh 20 payment.')
      return
    }
    setBusy(true)
    setError('')
    try {
      await api.post(`/cohorts/sponsored-view/assessments/${assessment.id}/payments/`, { payment_reference: reference })
      setPaymentReferences((current) => ({ ...current, [assessment.id]: '' }))
      await load()
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setBusy(false)
    }
  }

  const submitAttempt = async () => {
    if (!attempt) return
    setBusy(true)
    setError('')
    try {
      const { data } = await api.post(`/cohorts/sponsored-view/attempts/${attempt.id}/submit/`, { answers, reasoning })
      setAttempt(data)
      await load()
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setBusy(false)
    }
  }

  const reviewPayment = async (payment, decision) => {
    const transactionId = (transactionIds[payment.id] || '').trim()
    const rejectionReason = (rejectionReasons[payment.id] || '').trim()
    if (decision === 'verified' && !transactionId) {
      setError('Enter the confirmed M-Pesa transaction ID before verifying a payment.')
      return
    }
    if (decision === 'rejected' && !rejectionReason) {
      setError('Provide a reason when rejecting a payment.')
      return
    }
    setBusy(true)
    setError('')
    try {
      await api.post(`/cohorts/admin/sponsored-view/payments/${payment.id}/decision/`, {
        status: decision,
        mpesa_transaction_id: transactionId,
        rejection_reason: rejectionReason,
      })
      await load()
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setBusy(false)
    }
  }

  const updateAnswer = (questionId, answer) => setAnswers((current) => ({ ...current, [questionId]: answer }))
  const updateReasoning = (questionId, value) => setReasoning((current) => ({ ...current, [questionId]: value }))
  const attemptIsOpen = attempt?.status === 'in_progress' && remaining !== 0

  return <Page eyebrow="SPONSORED VIEW" title="Sponsored View Library" description="KSh 20 per attempt. Results and any reward remain subject to published rules, validation, funding, and approval.">
    <WeeklyScheduleNotice activity="sponsored_view" />
    <div className="library-summary"><strong>KSh 20 per attempt</strong><span>Maximum five paid attempts per student per day, Monday–Thursday · 10 questions per assessment · target 800 assessments / 8,000 questions</span></div>
    <div className="filter-row"><label>Study area<select name="field" value={filters.field} onChange={(event) => setFilters((current) => ({ ...current, field: event.target.value }))}><option value="">All areas</option>{studyAreas.map((area) => <option key={area}>{area}</option>)}</select></label><label>Week<select name="week" value={filters.week} onChange={(event) => setFilters((current) => ({ ...current, week: event.target.value }))}><option value="">All 8 weeks</option>{Array.from({ length: 8 }, (_, index) => <option key={index + 1} value={index + 1}>Week {index + 1}</option>)}</select></label><label>Topic<input maxLength={120} value={filters.topic} onChange={(event) => setFilters((current) => ({ ...current, topic: event.target.value }))} placeholder="Search titles and descriptions" /></label></div>
    {error && <div className="alert alert-error" role="alert">{error}</div>}
    {status.loading ? <Loading label="Finding published Sponsored View assessments…" /> : status.error ? <ErrorState message={status.error} retry={load} /> : assessments.length === 0 ? <Empty title="No complete, published Sponsored View assessments match these filters">No approved assessment content is currently available for this selection. The published content count is zero; no placeholder assessments are shown.</Empty> : <div className="content-grid">{assessments.map((assessment) => {
      const assessmentPayments = payments.filter((item) => item.assessment_id === assessment.id)
      const pendingPayment = assessmentPayments.find((item) => item.status === 'pending')
      const payment = assessmentPayments.find((item) => item.status === 'verified' && item.attempt?.status === 'in_progress')
        || assessmentPayments.find((item) => item.status === 'verified' && !item.attempt)
        || assessmentPayments.find((item) => item.status === 'verified')
        || pendingPayment
        || assessmentPayments[0]
      const locked = !assessment.has_verified_access
      const canRequestAnother = !pendingPayment && (
        !payment
        || payment.status === 'rejected'
        || ['graded', 'timed_out'].includes(payment.attempt?.status)
      )
      return <article className="tutorial-card sponsored-view-card" key={assessment.id}>
        <div className="tutorial-card-top"><span className="tag">{assessment.field}</span><span>Week {assessment.week}</span></div>
        <div className={`assessment-preview${locked ? ' assessment-preview-locked' : ''}`} aria-hidden={locked || undefined}>
          <h2>{assessment.title}</h2><p>{assessment.description}</p>
        </div>
        {locked && <p className="assessment-lock-notice" role="status">Preview locked until your KSh 20 payment is verified. Submit the payment reference below to request access.</p>}
        <p>{assessment.window_closes_at ? `Available now · closes ${new Date(assessment.window_closes_at).toLocaleString()}` : `Next opening: ${assessment.next_opening_at ? new Date(assessment.next_opening_at).toLocaleString() : 'not scheduled'}`}</p>
        <div className="tutorial-meta"><span>{assessment.question_count} questions</span><span>KSh {assessment.access_price_kes} per attempt</span></div>
        {payment && <p className={`contest-status status-${payment.status}`}>Payment: {payment.status.replaceAll('_', ' ')}{payment.rejection_reason ? ` — ${payment.rejection_reason}` : ''}</p>}
        {assessmentPayments.filter((item) => item.id !== payment?.id).map((otherPayment) => <p key={otherPayment.id}>Another attempt: payment {otherPayment.status.replaceAll('_', ' ')}{otherPayment.attempt?.score != null ? ` · score ${otherPayment.attempt.score}%` : ''}</p>)}
        {payment?.attempt && <p>Attempt: {payment.attempt.status.replaceAll('_', ' ')}{payment.attempt.score != null ? ` · Score ${payment.attempt.score}%` : ''}</p>}
        {payment?.status === 'verified' && <button className="button button-primary" disabled={busy || !assessment.can_start} onClick={() => beginAttempt(payment.id)}>{assessment.can_start ? payment.attempt?.status === 'in_progress' ? 'Resume assessment' : payment.attempt ? 'View result' : 'Start assessment' : 'Available Monday–Thursday'}</button>}
        {pendingPayment && <p role="status">Payment is awaiting administrator verification. Your library access will appear here as soon as it is verified.</p>}
        {canRequestAnother && <form className="form-stack" onSubmit={(event) => { event.preventDefault(); requestPayment(assessment) }}>
              <p>Pay KSh 20 to Till 1598106, then submit the M-Pesa payment reference. Access begins immediately after an administrator verifies payment.</p>
              <label>M-Pesa payment reference<input required maxLength={255} autoComplete="off" value={paymentReferences[assessment.id] || ''} onChange={(event) => setPaymentReferences((current) => ({ ...current, [assessment.id]: event.target.value }))} /></label>
              <button className="button button-primary" type="submit" disabled={busy || !assessment.window_closes_at}>{assessment.window_closes_at ? 'Submit payment for verification' : 'Payment access Monday–Thursday'}</button>
            </form>}
      </article>
    })}</div>}
    {attempt && <section className="panel sponsored-attempt" aria-labelledby="sponsored-attempt-title">
      <div className="contest-section-heading"><div><div className="eyebrow">{attempt.field}</div><h2 id="sponsored-attempt-title">{attempt.title}</h2></div><span className="contest-status">{attempt.status.replaceAll('_', ' ')}</span></div>
      {attempt.status === 'in_progress' && <p role="timer">Time remaining: {remaining == null ? '…' : `${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, '0')}`}</p>}
      {!attemptIsOpen && attempt.status === 'in_progress' && <p role="status">This timed attempt has expired or its access window has closed. Saved progress is retained; the server controls the final deadline.</p>}
      <div className="assessment-question-list">{attempt.questions.map((question) => <fieldset className="lesson-section" key={question.id} disabled={!attemptIsOpen || busy}>
        <legend><strong>{question.order}. {question.prompt}</strong></legend>
        {question.options.map((option) => <label className="assessment-option" key={option}><input type="radio" name={`sponsored-${question.id}`} checked={answers[question.id] === option || question.selected_answer === option} onChange={() => updateAnswer(question.id, option)} />{option}</label>)}
        {question.requires_reasoning && <label>Written reasoning<textarea maxLength={5000} required={attemptIsOpen} value={reasoning[question.id] || question.written_reasoning || ''} onChange={(event) => updateReasoning(question.id, event.target.value)} /></label>}
        {attempt.status === 'graded' && <p><strong>Correct answer:</strong> {question.correct_answer}<br />{question.rationale}</p>}
      </fieldset>)}</div>
      {attemptIsOpen && <button className="button button-primary" disabled={busy || answers && Object.keys(answers).length !== attempt.questions.length} onClick={submitAttempt}>{busy ? 'Submitting…' : 'Submit assessment'}</button>}
      {attempt.status === 'graded' && <p role="status">Final score: {attempt.score}%</p>}
    </section>}
    {isAdmin && <section className="panel admin-support-applications"><div className="contest-section-heading"><div><div className="eyebrow">ADMIN ONLY · PRIVATE PAYMENT DETAILS</div><h2>Sponsored View payment review</h2><p>Verify payment references against M-Pesa before granting access. Each verified payment grants one attempt.</p></div><button className="button button-quiet" onClick={load}>↻ Refresh</button></div>
      {adminError ? <ErrorState message={adminError} retry={load} /> : adminPayments.length === 0 ? <Empty title="No Sponsored View payments to review" /> : <div className="support-application-list">{adminPayments.map((payment) => <article className="support-application-status" key={payment.id}><strong>{payment.student_name} · {payment.assessment_title}</strong><span>{payment.status} · KSh {payment.amount_kes}</span><small>{payment.student_email} · {payment.field} · {payment.payment_reference}</small>{payment.status === 'pending' && <div className="form-stack">
        <label>Confirmed M-Pesa transaction ID<input required value={transactionIds[payment.id] || ''} onChange={(event) => setTransactionIds((current) => ({ ...current, [payment.id]: event.target.value }))} /></label>
        <button className="button button-primary" disabled={busy} onClick={() => reviewPayment(payment, 'verified')}>Verify payment and grant access</button>
        <label>Rejection reason<input required value={rejectionReasons[payment.id] || ''} onChange={(event) => setRejectionReasons((current) => ({ ...current, [payment.id]: event.target.value }))} /></label>
        <button className="button button-quiet" disabled={busy} onClick={() => reviewPayment(payment, 'rejected')}>Reject payment</button>
      </div>}</article>)}</div>}
    </section>}
  </Page>
}
