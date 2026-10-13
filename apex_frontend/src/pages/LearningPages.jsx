import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import api, { getErrorMessage, unwrapList } from '../api/client'
import { studyAreas } from '../data'
import Page from '../components/Page'
import { Empty, ErrorState, Loading, Unavailable } from '../components/States'

export function StudyAreas() {
  return <Page eyebrow="LEARN AT YOUR PACE" title="Choose a discipline" description="Explore an area to see published tutorials currently available from Apex.">
    <div className="discipline-grid study-grid">{studyAreas.map((area, index) => <Link key={area} to={`/study/${encodeURIComponent(area)}`} className="discipline-card"><span className="card-index">{String(index + 1).padStart(2, '0')}</span><strong>{area}</strong><span className="card-arrow">↗</span></Link>)}</div>
    <div className="info-note"><span>i</span><p>Tutorial availability depends on what has been published on the platform. Areas without published lessons will say so here.</p></div>
  </Page>
}

export function Tutorials() {
  const [params, setParams] = useState({ field: '', month: '', week: '' })
  const [items, setItems] = useState([])
  const [status, setStatus] = useState({ loading: true, error: '' })
  const load = async () => {
    setStatus({ loading: true, error: '' })
    try {
      const query = Object.fromEntries(Object.entries(params).filter(([, value]) => value))
      const { data } = await api.get('/cohorts/tutorials/', { params: query })
      setItems(unwrapList(data))
    } catch (error) {
      setStatus({ loading: false, error: getErrorMessage(error) })
      return
    }
    setStatus({ loading: false, error: '' })
  }
  useEffect(() => { load() }, [params.field, params.month, params.week])
  const update = (event) => setParams({ ...params, [event.target.name]: event.target.value })
  return <Page eyebrow="LEARNING LIBRARY" title="Tutorials" description="Published lessons from the Apex learning library. Content is shown only when returned by the platform.">
    <div className="filter-row"><label>Discipline<select name="field" value={params.field} onChange={update}><option value="">All areas</option>{studyAreas.map((area) => <option key={area}>{area}</option>)}</select></label><label>Month<input aria-label="Month" name="month" type="number" min="1" max="12" placeholder="Any" value={params.month} onChange={update} /></label><label>Week<input aria-label="Week" name="week" type="number" min="1" max="4" placeholder="Any" value={params.week} onChange={update} /></label></div>
    {status.loading ? <Loading label="Finding published tutorials…" /> : status.error ? <ErrorState message={status.error} retry={load} /> : items.length === 0 ? <Empty title="No published tutorials found">Try another discipline or come back when lessons are published.</Empty> : <div className="content-grid">{items.map((tutorial) => <TutorialCard key={tutorial.id} tutorial={tutorial} />)}</div>}
  </Page>
}

export function AreaTutorials() {
  const { area } = useParams()
  const field = decodeURIComponent(area || '')
  const [items, setItems] = useState([])
  const [status, setStatus] = useState({ loading: true, error: '' })
  const load = async () => {
    setStatus({ loading: true, error: '' })
    try {
      const { data } = await api.get('/cohorts/tutorials/', { params: { field } })
      setItems(unwrapList(data))
      setStatus({ loading: false, error: '' })
    } catch (error) { setStatus({ loading: false, error: getErrorMessage(error) }) }
  }
  useEffect(() => { load() }, [field])
  return <Page eyebrow="STUDY AREA" title={field} description="Published lessons available for this discipline.">
    <Link className="back-link inline-back" to="/study">← All study areas</Link>
    {status.loading ? <Loading label={`Loading ${field} tutorials…`} /> : status.error ? <ErrorState message={status.error} retry={load} /> : !items.length ? <Empty title="No published lessons in this area yet">Apex will show tutorials here when they are published for {field}.</Empty> : <div className="content-grid">{items.map((tutorial) => <TutorialCard key={tutorial.id} tutorial={tutorial} />)}</div>}
  </Page>
}

function TutorialCard({ tutorial }) {
  return <Link to={`/tutorials/${tutorial.id}`} className="tutorial-card"><div className="tutorial-card-top"><span className="tag">{tutorial.field}</span><span className="card-arrow">↗</span></div><h2>{tutorial.title}</h2><p>{tutorial.description}</p><div className="tutorial-meta"><span>{tutorial.difficulty || 'Lesson'}</span><span>{tutorial.duration_minutes ? `${tutorial.duration_minutes} min` : 'Duration not listed'}</span></div></Link>
}

export function TutorialDetail() {
  const { id } = useParams()
  const [item, setItem] = useState(null)
  const [status, setStatus] = useState({ loading: true, error: '' })
  const load = () => {
    setStatus({ loading: true, error: '' })
    api.get(`/cohorts/tutorials/${id}/`).then(({ data }) => { setItem(data); setStatus({ loading: false, error: '' }) }).catch((error) => setStatus({ loading: false, error: getErrorMessage(error) }))
  }
  useEffect(() => { load() }, [id])
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
    <div className="lesson-meta"><span className="tag">{item.difficulty}</span><span>Month {item.month} · Week {item.week}</span><span>{item.duration_minutes ? `${item.duration_minutes} minutes` : 'Duration not listed'}</span></div>
    {item.video_url && <div className="video-frame"><video controls preload="metadata" src={item.video_url}>Your browser does not support embedded video.</video></div>}
    {item.learning_objectives?.length > 0 && <section className="lesson-section"><div className="eyebrow">LEARNING OBJECTIVES</div><ul>{item.learning_objectives.map((objective, index) => <li key={`${index}-${objective}`}>{objective}</li>)}</ul></section>}
    {sections.length > 0 ? <div className="lesson-sections">{sections.map(([heading, content]) => <section className="lesson-section" key={heading}><h2>{heading}</h2><p>{content}</p></section>)}</div> : !item.video_url && <Unavailable title="Lesson content not available">This tutorial currently has no published lesson content.</Unavailable>}
    {item.questions?.length > 0 && <section className="lesson-section"><div className="eyebrow">CHECK YOUR UNDERSTANDING</div>{item.questions.map((question, index) => <div className="question-preview" key={question.id}><strong>{index + 1}. {question.prompt}</strong><ul>{question.options?.map((option, optionIndex) => <li key={optionIndex}>{option}</li>)}</ul></div>)}</section>}
  </Page>
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
  const [jobs, setJobs] = useState([])
  const [status, setStatus] = useState({ loading: true, error: '' })
  const load = () => {
    setStatus({ loading: true, error: '' })
    api.get('/vendor/opportunities/').then(({ data }) => { setJobs(unwrapList(data)); setStatus({ loading: false, error: '' }) }).catch((error) => setStatus({ loading: false, error: getErrorMessage(error) }))
  }
  useEffect(() => { load() }, [])
  return <Page eyebrow="NEXT STEPS" title="Opportunities" description="Open opportunities currently returned by the Apex platform. Eligibility and selection remain with the platform.">
    {status.loading ? <Loading label="Looking for open opportunities…" /> : status.error ? <ErrorState message={status.error} retry={load} /> : jobs.length === 0 ? <Empty title="No open opportunities right now">There are no open roles to display. Check back later.</Empty> : <div className="content-grid">{jobs.map((job) => <article key={job.id} className="opportunity-card"><div className="tutorial-card-top"><span className="tag">{job.profession_required}</span><span className="job-status">{job.status}</span></div><h2>{job.title}</h2><p>{job.description}</p><div className="budget">{job.currency || 'KES'} {job.budget_min ?? '—'} – {job.budget_max ?? '—'}</div><div className="tag-row">{(job.skills_required || []).map((skill) => <span key={skill} className="tag">{skill}</span>)}</div><div className="job-details"><span>Minimum merit: {job.min_trust_score ?? 0}</span><span>{job.deadline ? `Deadline ${new Date(job.deadline).toLocaleDateString()}` : 'No deadline listed'}</span></div></article>)}</div>}
  </Page>
}

export function SponsoredView() {
  return <Page eyebrow="SPONSORED VIEW" title="Your focused feed" description="Apex displays sponsored content only when it is supplied by an active platform service."><Unavailable title="Sponsored content is not connected">There is no sponsored-content API in the current backend. No promotions or funding have been fabricated here.</Unavailable><div className="sponsored-blank" aria-label="No sponsored content is currently connected"><span>◈</span><strong>Space reserved for verified partner content</strong><small>No placements are currently available.</small></div></Page>
}
