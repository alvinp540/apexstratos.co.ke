import { useCallback, useEffect, useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import api, { getErrorMessage, unwrapList } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { studyAreas } from '../data'
import { Loading } from '../components/States'
import Page from '../components/Page'
import { applyForSupportProgram, submitSupportApplicationInformation } from '../api/cohortAPI'
import SupportApplicationFields from '../components/SupportApplicationFields'

export function Landing() {
  return <div className="landing">
    <header className="landing-nav"><Link to="/" className="brand"><span className="brand-symbol">A</span><span>APEXSTRATOS<small>PROVE · PERFORM · PROGRESS</small></span></Link><nav aria-label="Public navigation"><a href="#approach">How it works</a><a href="#study-areas">Explore study areas</a><a href="#merit">Merit</a><a href="#opportunities">Opportunities</a><Link to="/login">Sign in</Link><Link className="button button-primary" to="/register">Get started <span>↗</span></Link><details className="landing-menu"><summary aria-label="Open navigation menu">Menu</summary><div className="landing-menu-links"><a href="#approach">How it works</a><a href="#study-areas">Explore study areas</a><a href="#merit">Merit</a><a href="#opportunities">Opportunities</a><Link to="/login">Sign in</Link></div></details></nav></header>
    <main>
      <section className="hero"><div className="hero-copy"><div className="eyebrow">CAPABILITY · EVIDENCE · OPPORTUNITY</div><h1>Prove.<br />Perform.<br /><em>Progress.</em></h1><p className="hero-support">Your capability can become your opportunity.</p><p>ApexStratos helps students learn, practise, demonstrate practical ability, build verified merit, and discover opportunities under clear eligibility rules.</p><div className="hero-actions"><Link className="button button-primary button-large" to="/register">Get started <span>↗</span></Link><a className="text-link" href="#approach">Explore how it works <span>→</span></a></div></div><div className="journey-card" aria-label="Student journey: Discover, Learn, Understand, Practise, Demonstrate, Earn Merit, Access Opportunities"><div className="eyebrow">YOUR CAPABILITY JOURNEY</div><ol>{['Discover', 'Learn', 'Understand', 'Practise', 'Demonstrate', 'Earn Merit', 'Access Opportunities'].map((stage, index) => <li key={stage}><span>{String(index + 1).padStart(2, '0')}</span>{stage}</li>)}</ol></div></section>
      <section id="approach" className="intro-section"><div><div className="eyebrow">HOW IT WORKS</div><h2>Learn, demonstrate,<br /><em>move forward.</em></h2></div><p>Capability grows through practice. Assessments create performance evidence, verified work can contribute to earned merit, and opportunities remain subject to their published eligibility and funding rules.</p></section>
      <section className="steps-grid" aria-label="ApexStratos programme stages">{[
        ['01', 'Develop capability', 'Use learning materials and practice to build useful skills.'],
        ['02', 'Demonstrate performance', 'Show what you can do through relevant, scenario-based assessments.'],
        ['03', 'Build merit', 'Merit reflects verified performance, consistency, improvement, and integrity.'],
        ['04', 'Explore opportunities', 'Review published opportunities and their actual eligibility rules.'],
      ].map(([number, title, description]) => <article className="step-card" key={number}><span>{number}</span><h3>{title}</h3><p>{description}</p></article>)}</section>
      <section id="study-areas" className="discipline-section"><div className="section-heading"><div><div className="eyebrow">TEN OFFICIAL STUDY AREAS</div><h2>Explore what you can learn</h2></div><Link className="text-link" to="/study">Explore all study areas <span>→</span></Link></div><div className="discipline-grid">{studyAreas.map((area, i) => <Link key={area} to={`/study/${encodeURIComponent(area)}`} className="discipline-card"><span className="card-index">{String(i + 1).padStart(2, '0')}</span><strong>{area}</strong><span className="card-arrow">↗</span></Link>)}</div></section>
      <section className="programme-note" id="merit"><div><div className="eyebrow">MERIT IS EARNED</div><h2>Payment is not merit.</h2></div><p>Fees may provide access to a specific paid programme after verification. They do not buy a score, rank, credibility, or guaranteed award. Verified performance and published rules determine recognition.</p><Link to="/merit" className="text-link">How merit works <span>→</span></Link></section>
      <section className="programme-note" id="opportunities"><div><div className="eyebrow">OPPORTUNITIES</div><h2>Eligibility comes first.</h2></div><p>Opportunities appear only when genuine listings are available. Selection, sponsorship, and funding are subject to each programme's disclosed rules; outcomes are never promised.</p><Link to="/opportunities" className="text-link">Explore opportunities <span>→</span></Link></section>
      <section className="closing-banner"><div><div className="eyebrow">START WITH YOUR CAPABILITY</div><h2>Your next useful step starts here.</h2></div><Link to="/register" className="button button-primary">Get started <span>↗</span></Link></section>
    </main><footer className="landing-footer"><Link to="/" className="brand"><span className="brand-symbol">A</span><span>APEXSTRATOS</span></Link><span>PROVE WHAT YOU CAN DO · BUILD MERIT · UNLOCK OPPORTUNITY</span><span>© ApexStratos</span></footer>
  </div>
}

export function AuthPage({ mode }) {
  const { user, login, register } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [form, setForm] = useState({ email: '', password: '', username: '', password2: '', phone_number: '', role: 'professional' })
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  if (user) return <Navigate to="/dashboard" replace />
  const update = (event) => setForm({ ...form, [event.target.name]: event.target.value })
  const submit = async (event) => {
    event.preventDefault()
    setError('')
    setMessage('')
    setBusy(true)
    try {
      if (mode === 'register') {
        const { data } = await register(form)
        setMessage(data.message || 'Registration successful. You can now sign in.')
      } else {
        await login({ email: form.email, password: form.password })
        navigate(params.get('next') || '/dashboard', { replace: true })
      }
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return <div className="auth-screen"><div className="auth-brand"><Link to="/" className="brand"><span className="brand-symbol">A</span><span>APEXSTRATOS</span></Link><span>PROVE · PERFORM · PROGRESS</span></div><div className="auth-panel"><div className="eyebrow">{mode === 'login' ? 'WELCOME BACK' : 'YOUR JOURNEY STARTS HERE'}</div><h1>{mode === 'login' ? 'Good to see you.' : 'Make room to grow.'}</h1><p>{mode === 'login' ? 'Sign in to pick up where you left off.' : 'Create an account to explore learning and opportunities.'}</p>
    {error && <div className="alert alert-error" role="alert">{error}</div>}{message && <div className="alert alert-success" role="status">{message}</div>}
    <form onSubmit={submit} className="form-stack">
      {mode === 'register' && <><label>Username<input name="username" autoComplete="username" required value={form.username} onChange={update} /></label><label>Account type<select name="role" value={form.role} onChange={update}><option value="professional">Student</option><option value="vendor">Organization / vendor</option></select></label></>}
      <label>Email address<input type="email" name="email" autoComplete="email" required value={form.email} onChange={update} /></label>
      {mode === 'register' && <label>Phone number <span className="optional">(optional)</span><input name="phone_number" autoComplete="tel" value={form.phone_number} onChange={update} /></label>}
      <label>Password<input type="password" name="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required minLength={mode === 'register' ? 8 : undefined} value={form.password} onChange={update} /></label>
      {mode === 'register' && <label>Confirm password<input type="password" name="password2" autoComplete="new-password" required value={form.password2} onChange={update} /></label>}
      <button className="button button-primary button-large full-width" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'} <span>↗</span></button>
    </form><div className="auth-switch">{mode === 'login' ? <>New to ApexStratos? <Link to="/register">Create an account</Link></> : <>Already a member? <Link to="/login">Sign in</Link></>}</div><Link to="/" className="back-link">← Back to ApexStratos</Link></div><div className="auth-footer">SECURE ACCESS · YOUR DATA STAYS YOURS</div></div>
}

export function Dashboard() {
  const { user } = useAuth()
  const [data, setData] = useState({})
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(true)
  const [guideData, setGuideData] = useState({ loading: true, errors: {}, ranking: null, contestRanking: null, leaders: [], programs: [], applications: [] })
  const [supportForms, setSupportForms] = useState({})
  const [applicationInfoForms, setApplicationInfoForms] = useState({})
  const [supportBusy, setSupportBusy] = useState('')
  const [supportError, setSupportError] = useState('')
  const guideStorageKey = `apexstratos.student-guide.dismissed.${user?.id || user?.username || 'student'}`
  const [guideVisible, setGuideVisible] = useState(() => {
    try { return window.localStorage.getItem(guideStorageKey) !== 'true' }
    catch { return true }
  })
  const load = useCallback(() => {
    setLoading(true)
    const requests = [
      ['profile', '/profiles/'], ['merit', '/trust/score/'],
      ['activity', user?.role === 'vendor' ? '/analytics/vendor/me/' : '/analytics/professional/me/'],
      ['tutorials', '/cohorts/tutorials/'],
    ]
    Promise.all(requests.map(async ([key, url]) => {
      try {
        const value = (await api.get(url)).data
        return [key, key === 'tutorials' ? unwrapList(value).length : value, '']
      }
      catch (err) { return [key, null, getErrorMessage(err)] }
    })).then((results) => {
      setData(Object.fromEntries(results.map(([key, value]) => [key, value])))
      setErrors(Object.fromEntries(results.filter(([, , error]) => error).map(([key, , error]) => [key, error])))
    }).finally(() => setLoading(false))
  }, [user?.role])
  useEffect(() => { load() }, [load])
  const loadGuideData = useCallback(async () => {
    const requests = [
      ['ranking', '/rankings/me/'],
      ['contestRanking', '/cohorts/contests/leaderboard/me/'],
      ['leaders', '/rankings/global/'],
      ['programs', '/cohorts/support/programs/'],
      ['applications', '/cohorts/support/applications/'],
    ]
    const results = await Promise.all(requests.map(async ([key, url]) => {
      try { return [key, (await api.get(url)).data, ''] }
      catch (error) { return [key, null, getErrorMessage(error)] }
    }))
    const values = Object.fromEntries(results.map(([key, value]) => [key, value]))
    setGuideData({
      loading: false,
      ranking: values.ranking,
      contestRanking: values.contestRanking,
      leaders: unwrapList(values.leaders),
      programs: unwrapList(values.programs),
      applications: unwrapList(values.applications),
      errors: Object.fromEntries(results.filter(([, , error]) => error).map(([key, , error]) => [key, error])),
    })
  }, [])
  useEffect(() => { loadGuideData() }, [loadGuideData])
  const submitSupportApplication = async (event, program) => {
    event.preventDefault()
    setSupportBusy(program.id)
    setSupportError('')
    try {
      const form = supportForms[program.id] || {}
      await applyForSupportProgram(program.id, {
        full_name: form.full_name || data.profile?.full_name || user?.full_name || '',
        registered_phone_number: form.registered_phone_number || user?.phone_number || '',
        mpesa_number: form.mpesa_number || '',
        application_data: form.application_data || {},
      })
      setSupportForms((current) => ({ ...current, [program.id]: {} }))
      await loadGuideData()
    } catch (error) {
      setSupportError(getErrorMessage(error))
    } finally {
      setSupportBusy('')
    }
  }
  const submitApplicationInformation = async (event, application) => {
    event.preventDefault()
    setSupportBusy(application.id)
    setSupportError('')
    try {
      const values = applicationInfoForms[application.id] || {}
      await submitSupportApplicationInformation(application.id, {
        mpesa_number: values.mpesa_number || application.mpesa_number,
        application_data: values.application_data || application.application_data || {},
      })
      setApplicationInfoForms((current) => ({ ...current, [application.id]: {} }))
      await loadGuideData()
    } catch (error) {
      setSupportError(getErrorMessage(error))
    } finally {
      setSupportBusy('')
    }
  }
  const dismissGuide = () => {
    setGuideVisible(false)
    try { window.localStorage.setItem(guideStorageKey, 'true') }
    catch { /* The guide remains dismissible for this page view. */ }
  }
  const reopenGuide = () => {
    setGuideVisible(true)
    try { window.localStorage.removeItem(guideStorageKey) }
    catch { /* The guide remains visible for this page view. */ }
  }
  const firstName = data.profile?.full_name?.split(' ')[0] || user?.username || 'there'
  return <Page eyebrow="YOUR LEARNING SPACE" title={`Welcome, ${firstName}.`} description="A clear view of your learning, verified progress, and next steps on ApexStratos.">
    <section className="support-programme-section" aria-label="Welcome to ApexStratos">
      <div className="eyebrow">WELCOME TO APEXSTRATOS</div>
      <h2>Welcome to ApexStratos — Prove what you can do. Build merit. Unlock opportunity.</h2>
      <p>ApexStratos helps you develop practical capability, demonstrate your performance, build verified merit and discover potential rewards, sponsorships and other opportunities. Payments or purchases never buy merit or guarantee an award.</p>
    </section>
    <div className="dashboard-highlight"><div><div className="eyebrow">KEEP MOVING FORWARD</div><h2>Small steps add up.</h2><p>Explore a tutorial, update your profile, or see what opportunities are open.</p><Link to="/study" className="button button-primary">Find your next lesson <span>↗</span></Link></div><div className="highlight-orbit" aria-hidden="true"><div /><span>01</span></div></div>
    <div className="section-heading compact"><h2>Your snapshot</h2><button className="text-button" onClick={load}>↻ Refresh</button></div>
    <div className="metric-grid">{[
      ['Merit score', data.merit?.overall_merit_score, data.merit?.tier ? `Tier ${data.merit.tier}` : 'From your trust record', 'merit', '/merit'],
      [user?.role === 'vendor' ? 'Jobs posted' : 'Published tutorials', user?.role === 'vendor' ? data.activity?.total_jobs_posted : data.tutorials, user?.role === 'vendor' ? 'Your vendor activity' : 'Available learning content', user?.role === 'vendor' ? 'activity' : 'tutorials', user?.role === 'vendor' ? '/opportunities' : '/tutorials'],
      ['Assessments completed', data.activity?.total_assessments, 'Recorded assessment activity', 'activity', '/contests'],
      ['Learning profile', data.profile?.headline || 'Add a short introduction', 'Your interests and capabilities', 'profile', '/profile'],
    ].map(([label, value, caption, key, to]) => <Link to={to} key={label} className="metric-card"><span className="metric-label">{label}</span>{loading ? <span className="metric-value metric-loading">···</span> : errors[key] ? <span className="metric-value metric-unavailable">Unavailable</span> : <strong className="metric-value">{value ?? '—'}</strong>}<span className="metric-caption">{caption}</span><span className="metric-arrow">↗</span></Link>)}</div>
    <div className="dashboard-bottom"><div className="panel"><div className="panel-heading"><h2>Pick a direction</h2><Link to="/study">All disciplines →</Link></div><div className="quick-links"><Link to="/tutorials"><span>▷</span><strong>Browse tutorials</strong><small>Learning content available on Apex</small><b>→</b></Link><Link to="/mentorship"><span>◎</span><strong>Meet mentors</strong><small>Explore mentors listed on Apex</small><b>→</b></Link><Link to="/opportunities"><span>⌁</span><strong>Find opportunities</strong><small>See open roles from the platform</small><b>→</b></Link></div></div><div className="panel profile-panel"><div className="eyebrow">YOUR PROFILE</div><h2>Show what you can do.</h2><p>Keep your skills and experience current so people can understand your work.</p><Link to="/profile" className="text-link">Review your profile <span>→</span></Link></div></div>
    {user?.role !== 'vendor' && <section className="support-programme-section" aria-labelledby="student-guide-title">
      <div className="section-heading compact"><div><div className="eyebrow">YOUR STUDENT GUIDE</div><h2 id="student-guide-title">A simple path forward</h2></div>{guideVisible ? <button className="text-button" onClick={dismissGuide}>Dismiss guide</button> : <button className="text-button" onClick={reopenGuide}>Show your steps</button>}</div>
      {guideVisible && <ol className="steps-grid">
        <li className="step-card"><span>01</span><h3>Choose a study area</h3><p>Pick the area that best matches what you want to learn.</p><Link className="text-link" to="/study">Choose a study area →</Link></li>
        <li className="step-card"><span>02</span><h3>Learn with free Tutorials</h3><p>Tutorials are scheduled Monday through Thursday.</p><Link className="text-link" to="/tutorials">Browse Tutorials →</Link></li>
        <li className="step-card"><span>03</span><h3>Explore Sponsored View</h3><p>Available Monday–Thursday at KSh 20 per attempt, with up to five attempts per day.</p><Link className="text-link" to="/sponsored-view">Open Sponsored View →</Link></li>
        <li className="step-card"><span>04</span><h3>Take the Main Contest</h3><p>Available Friday–Sunday after the applicable KSh 100 payment is verified.</p><Link className="text-link" to="/contests">View Main Contest →</Link></li>
        <li className="step-card"><span>05</span><h3>Review verified merit</h3><p>{guideData.errors.ranking ? 'Your merit ranking is currently unavailable.' : guideData.ranking ? `Your published global merit rank is #${guideData.ranking.global_rank}.` : 'No personal merit ranking record is currently available.'}</p>{guideData.errors.contestRanking ? <p role="status">Contest-cycle rank unavailable: {guideData.errors.contestRanking}</p> : guideData.contestRanking?.rank ? <p>Main Contest cycle: rank #{guideData.contestRanking.rank} of {guideData.contestRanking.participant_count} in {guideData.contestRanking.field}, average {guideData.contestRanking.average_score}%. Cycle {new Date(guideData.contestRanking.cycle_start).toLocaleDateString()}–{new Date(guideData.contestRanking.cycle_end).toLocaleDateString()} EAT.</p> : <p>{guideData.contestRanking?.ranking_method ? 'No verified Main Contest result is recorded for your cycle rank yet.' : ''}</p>}<Link className="text-link" to="/merit">Merit and leaderboard →</Link>
          {guideData.errors.leaders ? <p role="status">Leaderboard unavailable: {guideData.errors.leaders}</p> : guideData.leaders.length > 0 && <p>Current published leaderboard: {guideData.leaders.slice(0, 3).map((leader) => `${leader.full_name || 'Apex member'} (#${leader.global_rank})`).join(', ')}.</p>}
        </li>
        <li className="step-card"><span>06</span><h3>Check qualifying opportunities &amp; support</h3><p>See published programmes, your actual merit eligibility, and the reason for each result in the section below.</p><Link className="text-link" to="/opportunities">Open opportunities and support →</Link></li>
        <li className="step-card"><span>07</span><h3>Apply and track status</h3><p>Eligible students can submit the private application and payment-details form. Review decisions and payment status are tracked there; applying does not guarantee funding.</p><Link className="text-link" to="/opportunities">Open application and status tracking →</Link></li>
      </ol>}
    </section>}
    {user?.role !== 'vendor' && <section className="support-programme-section" aria-labelledby="dashboard-opportunities-title">
      <div className="section-heading compact"><div><div className="eyebrow">PUBLISHED PROGRAMMES</div><h2 id="dashboard-opportunities-title">Opportunities &amp; Support</h2></div><Link className="text-link" to="/opportunities">Applications and status tracking →</Link></div>
      {guideData.loading ? <p>Checking published programmes and your current eligibility…</p> : guideData.errors.programs ? <p role="status">Eligibility information is unavailable: {guideData.errors.programs}</p> : guideData.programs.length === 0 ? <p>Your opportunities will appear here as you participate, build verified merit and meet published eligibility requirements. Start by choosing a study area and completing your first eligible assessment. No support programmes are currently published.</p> : <div className="support-programme-list">{guideData.programs.map((program) => {
        const application = program.application
        const form = supportForms[program.id] || {}
        const reason = application
          ? `Application status: ${application.status.replaceAll('_', ' ')}.`
          : program.eligible
            ? `Eligible to apply: verified Main Contest merit is ${program.merit_score}% against the published ${program.merit_cutoff}% cutoff.`
            : program.eligibility_reason || `Not currently eligible under the published programme rules: ${program.eligibility_rules}`
        return <article className="support-programme-card" key={program.id}>
          <div className="tutorial-card-top"><h3>{program.title}</h3><span className={`contest-status status-${application?.status || (program.eligible ? 'eligible' : 'pending')}`}>{application?.status?.replaceAll('_', ' ') || (program.eligible ? 'Eligible to apply' : 'Not yet eligible')}</span></div>
          <p>{program.description}</p>
          <p>{reason}</p>
          <div className="support-programme-facts"><span>Published criterion: {program.metric_label ? `${program.metric_label} ≥ ${program.merit_cutoff}` : 'Eligibility rules need administrator configuration'}</span><span>{program.metric_label || 'Verified result'}: {program.merit_score} ({program.completed_requirements} qualifying records)</span><span>Funding: {program.funding_status.replaceAll('_', ' ')}</span>{program.deadline && <span>Deadline: {new Date(program.deadline).toLocaleString()}</span>}</div>
          <p className="support-eligibility-rules"><strong>Published eligibility rules:</strong> {program.eligibility_rules}</p>
          {application ? <div className="support-application-status"><strong>Application status: {application.status.replaceAll('_', ' ')}</strong>{application.admin_reason && <p>{application.admin_reason}</p>}{application.payment_confirmed_at && application.status === 'paid' && <p>Payment confirmed: {new Date(application.payment_confirmed_at).toLocaleString()}</p>}</div> : program.eligible && program.funding_status !== 'closed' && <form className="support-application-form" onSubmit={(event) => submitSupportApplication(event, program)}>
            <h3>Apply for this programme</h3><p>Submitting the form requests review. Eligibility is not a guarantee of selection, funding or payment.</p>
            <label>Registered full name<input required maxLength={200} autoComplete="name" value={form.full_name ?? data.profile?.full_name ?? user?.full_name ?? ''} onChange={(event) => setSupportForms((current) => ({ ...current, [program.id]: { ...current[program.id], full_name: event.target.value } }))} /></label>
            <label>Registered phone number<input required maxLength={20} autoComplete="tel" value={form.registered_phone_number ?? user?.phone_number ?? ''} onChange={(event) => setSupportForms((current) => ({ ...current, [program.id]: { ...current[program.id], registered_phone_number: event.target.value } }))} /></label>
            <label>M-Pesa payment number<input required maxLength={20} autoComplete="tel" value={form.mpesa_number || ''} onChange={(event) => setSupportForms((current) => ({ ...current, [program.id]: { ...current[program.id], mpesa_number: event.target.value } }))} /></label>
            <SupportApplicationFields
              fields={program.application_fields}
              values={form.application_data || {}}
              onChange={(key, value) => setSupportForms((current) => ({
                ...current,
                [program.id]: {
                  ...current[program.id],
                  application_data: { ...current[program.id]?.application_data, [key]: value },
                },
              }))}
            />
            {supportError && <div className="alert alert-error" role="alert">{supportError}</div>}
            <button className="button button-primary" disabled={supportBusy === program.id}>{supportBusy === program.id ? 'Submitting…' : 'Submit application'}</button>
          </form>}
        </article>
      })}</div>}
      {!guideData.loading && !guideData.errors.applications && guideData.applications.length > 0 && <div className="support-applications-section"><h3>Your application and payment status</h3><div className="support-application-list">{guideData.applications.map((application) => {
        const values = applicationInfoForms[application.id] || {}
        return <article className="support-application-status" key={application.id}><strong>{application.program_title}</strong><span>{application.status.replaceAll('_', ' ')}</span><small>Submitted {new Date(application.submitted_at).toLocaleString()}</small>{application.admin_reason && <p>{application.admin_reason}</p>}{application.application_fields_at_application?.map((field) => application.application_data?.[field.key] && <p key={field.key}><strong>{field.label}:</strong> {application.application_data[field.key]}</p>)}{application.status === 'paid' && application.payment_confirmed_at && <p>Payment confirmed {new Date(application.payment_confirmed_at).toLocaleString()}</p>}{application.status === 'awaiting_information' && <form className="support-application-form" onSubmit={(event) => submitApplicationInformation(event, application)}><label>M-Pesa payment number<input required maxLength={20} autoComplete="tel" value={values.mpesa_number ?? application.mpesa_number} onChange={(event) => setApplicationInfoForms((current) => ({ ...current, [application.id]: { ...current[application.id], mpesa_number: event.target.value } }))} /></label><SupportApplicationFields fields={application.application_fields_at_application} values={values.application_data ?? application.application_data ?? {}} onChange={(key, value) => setApplicationInfoForms((current) => ({ ...current, [application.id]: { ...current[application.id], application_data: { ...current[application.id]?.application_data, [key]: value } } }))} />{supportError && <div className="alert alert-error" role="alert">{supportError}</div>}<button className="button button-primary" disabled={supportBusy === application.id}>{supportBusy === application.id ? 'Submitting…' : 'Submit requested information'}</button></form>}<ol>{(application.events || []).map((event, index) => <li key={`${event.status}-${event.created_at}-${index}`}>{event.status.replaceAll('_', ' ')} · {new Date(event.created_at).toLocaleString()}{event.reason && ` — ${event.reason}`}</li>)}</ol></article>
      })}</div></div>}
    </section>}
    {loading && <div className="visually-hidden"><Loading /></div>}
  </Page>
}
