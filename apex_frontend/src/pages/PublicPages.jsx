import { useEffect, useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import api, { getErrorMessage, unwrapList } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { studyAreas } from '../data'
import { Loading } from '../components/States'
import Page from '../components/Page'

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
  const load = () => {
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
  }
  useEffect(() => { load() }, [])
  const firstName = data.profile?.full_name?.split(' ')[0] || user?.username || 'there'
  return <Page eyebrow="YOUR LEARNING SPACE" title={`Welcome, ${firstName}.`} description="A clear view of your learning, verified progress, and next steps on ApexStratos.">
    <div className="dashboard-highlight"><div><div className="eyebrow">KEEP MOVING FORWARD</div><h2>Small steps add up.</h2><p>Explore a tutorial, update your profile, or see what opportunities are open.</p><Link to="/study" className="button button-primary">Find your next lesson <span>↗</span></Link></div><div className="highlight-orbit" aria-hidden="true"><div /><span>01</span></div></div>
    <div className="section-heading compact"><h2>Your snapshot</h2><button className="text-button" onClick={load}>↻ Refresh</button></div>
    <div className="metric-grid">{[
      ['Merit score', data.merit?.overall_merit_score, data.merit?.tier ? `Tier ${data.merit.tier}` : 'From your trust record', 'merit', '/merit'],
      [user?.role === 'vendor' ? 'Jobs posted' : 'Published tutorials', user?.role === 'vendor' ? data.activity?.total_jobs_posted : data.tutorials, user?.role === 'vendor' ? 'Your vendor activity' : 'Available learning content', user?.role === 'vendor' ? 'activity' : 'tutorials', user?.role === 'vendor' ? '/opportunities' : '/tutorials'],
      ['Assessments completed', data.activity?.total_assessments, 'Recorded assessment activity', 'activity', '/contests'],
      ['Learning profile', data.profile?.headline || 'Add a short introduction', 'Your interests and capabilities', 'profile', '/profile'],
    ].map(([label, value, caption, key, to]) => <Link to={to} key={label} className="metric-card"><span className="metric-label">{label}</span>{loading ? <span className="metric-value metric-loading">···</span> : errors[key] ? <span className="metric-value metric-unavailable">Unavailable</span> : <strong className="metric-value">{value ?? '—'}</strong>}<span className="metric-caption">{caption}</span><span className="metric-arrow">↗</span></Link>)}</div>
    <div className="dashboard-bottom"><div className="panel"><div className="panel-heading"><h2>Pick a direction</h2><Link to="/study">All disciplines →</Link></div><div className="quick-links"><Link to="/tutorials"><span>▷</span><strong>Browse tutorials</strong><small>Learning content available on Apex</small><b>→</b></Link><Link to="/mentorship"><span>◎</span><strong>Meet mentors</strong><small>Explore mentors listed on Apex</small><b>→</b></Link><Link to="/opportunities"><span>⌁</span><strong>Find opportunities</strong><small>See open roles from the platform</small><b>→</b></Link></div></div><div className="panel profile-panel"><div className="eyebrow">YOUR PROFILE</div><h2>Show what you can do.</h2><p>Keep your skills and experience current so people can understand your work.</p><Link to="/profile" className="text-link">Review your profile <span>→</span></Link></div></div>
    {loading && <div className="visually-hidden"><Loading /></div>}
  </Page>
}
