import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api, { getErrorMessage, unwrapList } from '../api/client'
import { useAuth } from '../context/AuthContext'
import Page from '../components/Page'
import { Empty, ErrorState, Loading, Unavailable } from '../components/States'

function safeActionUrl(value) {
  if (typeof value !== 'string') return null
  if (value.startsWith('/') && !value.startsWith('//') && !value.startsWith('/\\')) return value
  try {
    const url = new URL(value)
    return url.protocol === 'https:' ? url.href : null
  } catch {
    return null
  }
}

export function Merit() {
  const [score, setScore] = useState(null)
  const [history, setHistory] = useState([])
  const [ranking, setRanking] = useState(null)
  const [leaders, setLeaders] = useState([])
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(true)
  const load = async () => {
    setLoading(true)
    const requests = [
      ['score', '/trust/score/'], ['history', '/trust/score/history/'],
      ['ranking', '/rankings/me/'], ['leaders', '/rankings/global/'],
    ]
    const results = await Promise.all(requests.map(async ([key, url]) => {
      try { return [key, (await api.get(url)).data, ''] }
      catch (error) { return [key, null, getErrorMessage(error)] }
    }))
    const next = Object.fromEntries(results.map(([key, value]) => [key, value]))
    setScore(next.score)
    setHistory(unwrapList(next.history))
    setRanking(next.ranking)
    setLeaders(unwrapList(next.leaders))
    setErrors(Object.fromEntries(results.filter(([, , error]) => error).map(([key, , error]) => [key, error])))
    setLoading(false)
  }
  useEffect(() => { load() }, [])
  return <Page eyebrow="YOUR WORK, REFLECTED" title="Merit & rankings" description="Trust and ranking data returned by Apex. Scores and placements are calculated by the platform.">
    {loading ? <Loading label="Loading your merit record…" /> : errors.score && errors.ranking ? <ErrorState message={`${errors.score} ${errors.ranking}`} retry={load} /> : <><div className="merit-overview"><div className="merit-score"><span className="eyebrow">OVERALL MERIT SCORE</span>{errors.score ? <strong className="metric-unavailable">Unavailable</strong> : score ? <><strong>{score.overall_merit_score}</strong><span className="tier-badge">{score.tier || 'Tier not listed'}</span><small>Last calculated {score.last_calculated ? new Date(score.last_calculated).toLocaleDateString() : 'not listed'}</small></> : <Empty title="No merit score yet">Apex has not returned a trust record for this account.</Empty>}</div><div className="rank-card"><span className="eyebrow">GLOBAL RANK</span>{errors.ranking ? <strong className="metric-unavailable">Unavailable</strong> : ranking ? <><strong>#{ranking.global_rank}</strong><span>{ranking.rank_movement > 0 ? `↑ ${ranking.rank_movement}` : ranking.rank_movement < 0 ? `↓ ${Math.abs(ranking.rank_movement)}` : 'No movement recorded'}</span><small>{ranking.profession || 'Profession not set'}</small></> : <span>No ranking record available.</span>}</div></div>
      {score && <div className="score-components">{[['PSP consistency', score.psp_consistency_score], ['Cohort performance', score.cohort_performance_score], ['Vendor ratings', score.vendor_rating_score], ['Authenticity confidence', score.authenticity_confidence]].map(([label, value]) => <div className="score-component" key={label}><span>{label}</span><strong>{value ?? '—'}</strong></div>)}</div>}
      <div className="dashboard-bottom merit-lower"><section className="panel"><div className="panel-heading"><h2>Global leaderboard</h2><span className="soft-label">Platform rankings</span></div>{errors.leaders ? <ErrorState message={errors.leaders} retry={load} /> : leaders.length ? <div className="leader-list">{leaders.slice(0, 10).map((leader) => <div className="leader-row" key={leader.id}><span className="leader-rank">#{leader.global_rank}</span><span className="leader-name">{leader.full_name || 'Apex member'}<small>{leader.profession || 'Profession not listed'}</small></span><strong>{leader.overall_merit_score ?? '—'}</strong><span className="tier-badge">{leader.tier || '—'}</span></div>)}</div> : <Empty title="No leaderboard records">Rankings will appear here if the platform has published them.</Empty>}</section><section className="panel"><div className="panel-heading"><h2>Merit history</h2></div>{errors.history ? <ErrorState message={errors.history} retry={load} /> : history.length ? <div className="history-list">{history.map((entry) => <div className="history-row" key={entry.id}><span className="history-dot" /><div><strong>{entry.overall_merit_score}</strong><small>{entry.reason || 'Score update'} · {entry.recorded_at ? new Date(entry.recorded_at).toLocaleDateString() : ''}</small></div></div>)}</div> : <Empty title="No score history yet">Score changes will show when returned by the platform.</Empty>}</section></div>
    </>}
  </Page>
}

const profileFields = [
  ['full_name', 'Full name'], ['headline', 'Headline'], ['profession', 'Profession'],
  ['location', 'Location'], ['country', 'Country'], ['phone_number', 'Phone number'], ['bio', 'About you'],
  ['years_experience', 'Years of experience'], ['portfolio_url', 'Portfolio URL'],
  ['linkedin_url', 'LinkedIn URL'],
]

export function Profile() {
  const { user } = useAuth()
  const [profile, setProfile] = useState(null)
  const [form, setForm] = useState({})
  const [status, setStatus] = useState({ loading: true, error: '', success: '' })
  const load = () => {
    setStatus({ loading: true, error: '', success: '' })
    api.get('/profiles/').then(({ data }) => {
      setProfile(data)
      setForm({ ...data, skillsText: Array.isArray(data.skills) ? data.skills.join(', ') : '', highlightsText: Array.isArray(data.highlights) ? data.highlights.join('\n') : '' })
      setStatus({ loading: false, error: '', success: '' })
    }).catch((error) => setStatus({ loading: false, error: getErrorMessage(error), success: '' }))
  }
  useEffect(() => { load() }, [])
  const save = async (event) => {
    event.preventDefault()
    setStatus({ loading: false, error: '', success: '', saving: true })
    const payload = {
      full_name: form.full_name || '',
      headline: form.headline || '',
      profession: form.profession || '',
      location: form.location || '',
      country: form.country || '',
      phone_number: form.phone_number || '',
      bio: form.bio || '',
      years_experience: Number(form.years_experience || 0),
      portfolio_url: form.portfolio_url || '',
      linkedin_url: form.linkedin_url || '',
      skills: form.skillsText.split(',').map((value) => value.trim()).filter(Boolean),
      highlights: form.highlightsText.split('\n').map((value) => value.trim()).filter(Boolean),
      show_whatsapp: Boolean(form.show_whatsapp),
    }
    try {
      const { data } = await api.patch('/profiles/', payload)
      setProfile(data)
      setForm({ ...data, skillsText: Array.isArray(data.skills) ? data.skills.join(', ') : '', highlightsText: Array.isArray(data.highlights) ? data.highlights.join('\n') : '' })
      setStatus({ loading: false, error: '', success: 'Profile changes saved.', saving: false })
    } catch (error) { setStatus({ loading: false, error: getErrorMessage(error), success: '', saving: false }) }
  }
  if (status.loading) return <Page eyebrow="YOUR PROFILE" title="Profile"><Loading /></Page>
  if (status.error && !profile) return <Page eyebrow="YOUR PROFILE" title="Profile"><ErrorState message={status.error} retry={load} /></Page>
  const change = (event) => setForm({ ...form, [event.target.name]: event.target.type === 'checkbox' ? event.target.checked : event.target.value })
  return <Page eyebrow="YOUR PROFILE" title="Profile" description="Keep your details current. Public profile fields are determined by Apex.">
    {status.error && <div className="alert alert-error" role="alert">{status.error}</div>}{status.success && <div className="alert alert-success" role="status">{status.success}</div>}
    <div className="profile-layout"><form className="panel form-stack profile-form" onSubmit={save}><div className="panel-heading"><h2>Profile details</h2><span className="soft-label">{profile.role || user?.role}</span></div>
      {profileFields.map(([name, label]) => <label key={name}>{label}<input name={name} type={name === 'years_experience' ? 'number' : name.endsWith('_url') ? 'url' : 'text'} min={name === 'years_experience' ? 0 : undefined} value={form[name] ?? ''} onChange={change} /></label>)}
      <label>Skills <span className="optional">(separate with commas)</span><input name="skillsText" value={form.skillsText ?? ''} onChange={change} /></label>
      <label>Highlights <span className="optional">(one per line)</span><textarea name="highlightsText" rows="4" value={form.highlightsText ?? ''} onChange={change} /></label>
      <label className="checkbox-label"><input type="checkbox" name="show_whatsapp" checked={Boolean(form.show_whatsapp)} onChange={change} />Show WhatsApp contact link on my public profile</label>
      <button className="button button-primary" disabled={status.saving}>{status.saving ? 'Saving…' : 'Save profile'} <span>↗</span></button>
    </form><aside className="panel profile-aside"><div className="profile-large-avatar">{(profile.full_name || user?.username || 'A')[0].toUpperCase()}</div><h2>{profile.full_name || user?.username}</h2><p>{profile.headline || 'Add a headline to introduce yourself.'}</p>{profile.skills?.length > 0 && <div className="tag-row">{profile.skills.map((skill) => <span key={skill} className="tag">{skill}</span>)}</div>}<div className="profile-detail"><span>Account email</span><strong>{profile.email || user?.email}</strong></div><div className="profile-detail"><span>Availability</span><strong>{profile.availability || 'Not listed'}</strong></div><Link to="/merit" className="text-link">View merit record <span>→</span></Link></aside></div>
  </Page>
}

export function Notifications() {
  const [items, setItems] = useState([])
  const [status, setStatus] = useState({ loading: true, error: '' })
  const load = () => {
    setStatus({ loading: true, error: '' })
    api.get('/notifications/').then(({ data }) => { setItems(unwrapList(data)); setStatus({ loading: false, error: '' }) }).catch((error) => setStatus({ loading: false, error: getErrorMessage(error) }))
  }
  useEffect(() => { load() }, [])
  const markOne = async (item) => {
    if (item.is_read) return
    try { await api.patch(`/notifications/${item.id}/read/`); setItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, is_read: true } : entry)) }
    catch (error) { setStatus({ ...status, error: getErrorMessage(error) }) }
  }
  const markAll = async () => {
    try { await api.post('/notifications/read-all/'); setItems((current) => current.map((item) => ({ ...item, is_read: true }))) }
    catch (error) { setStatus({ ...status, error: getErrorMessage(error) }) }
  }
  return <Page eyebrow="YOUR UPDATES" title="Notifications" description="Messages and updates returned for your account." action={items.some((item) => !item.is_read) && <button className="button button-quiet" onClick={markAll}>Mark all read</button>}>
    {status.error && <div className="alert alert-error">{status.error}</div>}{status.loading ? <Loading label="Loading notifications…" /> : status.error && !items.length ? <ErrorState message={status.error} retry={load} /> : items.length === 0 ? <Empty title="You're all caught up">Notifications will appear here when Apex sends them.</Empty> : <div className="notification-list">{items.map((item) => { const actionUrl = safeActionUrl(item.action_url); const external = actionUrl?.startsWith('https://'); return <article key={item.id} className={`notification-row${item.is_read ? '' : ' unread'}`}><span className="notification-icon">{item.is_read ? '◦' : '●'}</span><div className="notification-copy"><div className="notification-title"><strong>{item.title}</strong><span className="tag">{item.notification_type}</span></div><p>{item.message}</p><small>{item.created_at ? new Date(item.created_at).toLocaleString() : ''}</small>{actionUrl && <a href={actionUrl} className="text-link" target={external ? '_blank' : undefined} rel={external ? 'noreferrer noopener' : undefined}>Open update →</a>}</div>{!item.is_read && <button className="text-button" onClick={() => markOne(item)}>Mark read</button>}</article>})}</div>}
  </Page>
}

export function Admin() {
  const { user } = useAuth()
  const [users, setUsers] = useState([])
  const [logs, setLogs] = useState([])
  const [status, setStatus] = useState({ loading: true, error: '' })
  const load = async () => {
    setStatus({ loading: true, error: '' })
    try {
      const [userData, logData] = await Promise.all([api.get('/admin/users/'), api.get('/admin/fraud-logs/')])
      setUsers(unwrapList(userData.data))
      setLogs(unwrapList(logData.data))
      setStatus({ loading: false, error: '' })
    } catch (error) { setStatus({ loading: false, error: getErrorMessage(error) }) }
  }
  useEffect(() => { load() }, [])
  if (!user?.is_admin) return <Page eyebrow="RESTRICTED AREA" title="Admin tools"><Unavailable title="Admin access required">These tools are restricted by the backend. Sign in with an authorized admin account to continue.</Unavailable></Page>
  return <Page eyebrow="PLATFORM OPERATIONS" title="Admin tools" description="Administrative information is fetched from permission-protected Apex endpoints." action={<Link className="button button-quiet" to="/contests#main-contest-payments">Review contest payments <span>↗</span></Link>}>
    {status.loading ? <Loading label="Loading admin records…" /> : status.error ? <ErrorState message={status.error} retry={load} /> :     <div className="dashboard-bottom"><section className="panel"><div className="panel-heading"><h2>Users</h2><span className="soft-label">{users.length} on this page</span></div>{users.length ? <div className="admin-list">{users.map((entry) => <div key={entry.id} className="admin-row"><div><strong>{entry.username}</strong><small>{entry.email}</small></div><span className="tag">{entry.role}</span><span className={entry.is_email_verified ? 'status-ok' : 'status-warn'}>{entry.is_email_verified ? 'Verified' : 'Unverified'}</span></div>)}</div> : <Empty title="No users returned" />}</section><section className="panel"><div className="panel-heading"><h2>Fraud review</h2><span className="soft-label">{logs.length} on this page</span></div>{logs.length ? <div className="admin-list">{logs.map((entry) => <article key={entry.id} className="admin-log"><strong>{entry.event_type || 'Review record'}{entry.severity ? ` · ${entry.severity}` : ''}</strong><p>{entry.description || 'No further detail provided.'}</p><span>{entry.created_at ? new Date(entry.created_at).toLocaleString() : ''}</span><span className={entry.is_resolved ? 'status-ok' : 'status-warn'}>{entry.is_resolved ? 'Resolved' : 'Open'}</span></article>)}</div> : <Empty title="No fraud logs returned">There are no records to show on this page.</Empty>}</section></div>}
  </Page>
}
