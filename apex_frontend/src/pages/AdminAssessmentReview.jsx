import { useCallback, useEffect, useState } from 'react'
import api, { getErrorMessage, unwrapList } from '../api/client'
import { Empty, ErrorState, Loading, PaginationControls } from '../components/States'
import './AdminAssessmentReview.css'

const LIBRARIES = [
  { value: 'tutorials', label: 'Tutorials' },
  { value: 'main-contest', label: 'Main Contest' },
  { value: 'sponsored-view', label: 'Sponsored View' },
]

const STATUSES = ['draft', 'in_review', 'approved', 'scheduled', 'published', 'archived']

function availableActions(item) {
  if (item.library === 'sponsored-view') {
    return item.status === 'draft' ? ['publish'] : item.status === 'published' ? ['archive'] : []
  }
  if (item.status === 'draft') return ['submit_for_review']
  if (item.status === 'in_review') return ['approve']
  if (item.status === 'approved' || item.status === 'scheduled') return ['publish']
  if (item.status === 'published') return ['archive']
  return []
}

const ACTION_LABELS = {
  submit_for_review: 'Submit for review',
  approve: 'Approve',
  publish: 'Publish',
  archive: 'Archive',
}

export default function AdminAssessmentReview() {
  const [library, setLibrary] = useState('tutorials')
  const [contentStatus, setContentStatus] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [items, setItems] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [busyAction, setBusyAction] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get('/cohorts/admin/content/', {
        params: {
          library,
          page,
          ...(contentStatus ? { status: contentStatus } : {}),
          ...(search.trim() ? { search: search.trim() } : {}),
        },
      })
      const results = unwrapList(data)
      setItems(results)
      setTotal(data?.count ?? results.length)
      setSelectedId((current) => results.some((item) => item.id === current) ? current : results[0]?.id || '')
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }, [contentStatus, library, page, search])

  useEffect(() => { load() }, [load])

  const selected = items.find((item) => item.id === selectedId)

  const runAction = async (action) => {
    if (!selected) return
    if (['publish', 'archive'].includes(action) && !window.confirm(`${ACTION_LABELS[action]} “${selected.title}”?`)) return
    setBusyAction(action)
    setActionError('')
    try {
      const { data } = await api.post(
        `/cohorts/admin/content/${selected.library}/${selected.id}/`,
        { action },
      )
      setItems((current) => current.map((item) => item.id === data.id ? data : item))
    } catch (requestError) {
      setActionError(getErrorMessage(requestError))
    } finally {
      setBusyAction('')
    }
  }

  const changeLibrary = (event) => {
    setLibrary(event.target.value)
    setPage(1)
    setSelectedId('')
  }

  const changeStatus = (event) => {
    setContentStatus(event.target.value)
    setPage(1)
    setSelectedId('')
  }

  return <section className="assessment-review">
    <div className="panel assessment-review-filters">
      <label>Library<select value={library} onChange={changeLibrary}>{LIBRARIES.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
      <label>Status<select value={contentStatus} onChange={changeStatus}><option value="">All statuses</option>{STATUSES.map((value) => <option key={value} value={value}>{value.replace('_', ' ')}</option>)}</select></label>
      <label>Search<input value={search} maxLength={120} placeholder="Title or study area" onChange={(event) => { setSearch(event.target.value); setPage(1) }} /></label>
      <button className="button button-quiet" type="button" onClick={load} disabled={loading}>Refresh</button>
    </div>

    {error ? <ErrorState message={error} retry={load} /> : loading ? <Loading label="Loading assessment review queue…" /> : !items.length ? <Empty title="No assessments found">Try another library, status, or search term.</Empty> : <div className="assessment-review-layout">
      <section className="panel assessment-review-queue">
        <div className="panel-heading"><h2>Review queue</h2><span className="soft-label">{total} assessments</span></div>
        <div className="assessment-review-items">{items.map((item) => <button
          className={`assessment-review-item${item.id === selectedId ? ' selected' : ''}`}
          type="button"
          key={item.id}
          onClick={() => { setSelectedId(item.id); setActionError('') }}
        >
          <strong>{item.title}</strong><span>{item.field}</span><span className="tag">{item.status.replace('_', ' ')}</span>
        </button>)}</div>
        <PaginationControls page={page} total={total} onPageChange={setPage} />
      </section>

      {selected && <article className="panel assessment-review-detail">
        <div className="panel-heading"><h2>{selected.title}</h2><span className="tag">{selected.status.replace('_', ' ')}</span></div>
        <p className="soft-label">{selected.field} · {selected.library.replace('-', ' ')}{selected.week ? ` · Week ${selected.week}` : ''}{selected.slot ? ` · Slot ${selected.slot}` : ''}</p>
        <p>{selected.description}</p>
        {selected.scheduled_for && <p><strong>Scheduled:</strong> {new Date(selected.scheduled_for).toLocaleString()}</p>}
        <h3>Learning objectives</h3>
        {selected.learning_objectives?.length ? <ul>{selected.learning_objectives.map((objective, index) => <li key={`${index}-${objective}`}>{objective}</li>)}</ul> : <p>None provided.</p>}
        {selected.teaching_sections && Object.entries(selected.teaching_sections).map(([name, text]) => <section className="assessment-review-section" key={name}><h3>{name.replaceAll('_', ' ')}</h3><p>{text || 'Missing'}</p></section>)}
        {selected.quality_errors?.length > 0 && <div className="alert alert-error"><strong>Readiness checks</strong><ul>{selected.quality_errors.map((message) => <li key={message}>{message}</li>)}</ul></div>}
        {selected.field && ['Medical and Health', 'Law and Society'].includes(selected.field) && <p className={selected.expert_reviewed ? 'status-ok' : 'status-warn'}>{selected.expert_reviewed ? 'Expert review recorded' : 'Qualified expert review is required before approval or publication.'}</p>}
        <h3>Questions and answer key (admin only)</h3>
        {selected.questions.map((question) => <section className="assessment-review-question" key={question.id}>
          <strong>{question.order}. {question.prompt}</strong>
          <ul>{question.options?.map((option) => <li key={option}>{option}{option === question.correct_answer ? ' — correct answer' : ''}</li>)}</ul>
          <p><strong>Explanation:</strong> {question.rationale || 'Missing'}</p>
        </section>)}
        {actionError && <div className="alert alert-error" role="alert">{actionError}</div>}
        <div className="assessment-review-actions">{availableActions(selected).map((action) => <button
          className={action === 'publish' ? 'button button-primary' : 'button button-quiet'}
          type="button"
          key={action}
          disabled={Boolean(busyAction)}
          onClick={() => runAction(action)}
        >{busyAction === action ? 'Working…' : ACTION_LABELS[action]}</button>)}</div>
      </article>}
    </div>}
  </section>
}
