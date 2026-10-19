import { useState, useEffect } from 'react'
import Navbar from '../components/common/Navbar'
import JobPostForm from '../components/vendor/JobPostForm'
import MatchedProfessionals from '../components/vendor/MatchedProfessionals'
import EscrowFundWidget from '../components/vendor/EscrowFundWidget'
import { getVendorJobs, publishJob, getVendorDashboard } from '../api/vendorAPI'
import { formatCurrency, formatDate } from '../utils/formatters'
import StatCard from '../components/common/StatCard'
import LoadingSpinner from '../components/common/LoadingSpinner'
import toast from 'react-hot-toast'

export default function VendorPortalPage() {
  const [jobs, setJobs] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [view, setView] = useState('dashboard')
  const [selectedJob, setSelectedJob] = useState(null)

  const loadData = async () => {
    setLoading(true)
    try {
      const [jobsRes, statsRes] = await Promise.all([getVendorJobs(), getVendorDashboard()])
      setJobs(jobsRes.data)
      setStats(statsRes.data)
    } catch (error) {
      console.error('Could not load vendor dashboard.', error)
      toast.error(error.response?.data?.detail || 'Could not load vendor dashboard.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [])

  const handlePublish = async (jobId) => {
    try {
      await publishJob(jobId)
      toast.success('Job published! Routing initiated.')
      loadData()
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Publish failed.')
    }
  }

  const STATUS_COLORS = { draft: '#94a3b8', open: 'var(--color-success)', matched: 'var(--color-warning)', in_progress: 'var(--color-primary)', completed: 'var(--color-accent)', cancelled: 'var(--color-error)' }

  return (
    <>
      <Navbar />
      <div className="page-container">
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
          {['dashboard', 'post', 'jobs'].map((v) => (
            <button key={v} onClick={() => setView(v)} style={{
              background: view === v ? 'var(--color-primary)' : 'var(--color-border)',
              color: view === v ? '#fff' : 'var(--color-text)',
              textTransform: 'capitalize',
            }}>
              {v === 'post' ? 'Post a Job' : v === 'jobs' ? 'My Jobs' : 'Dashboard'}
            </button>
          ))}
        </div>

        {view === 'dashboard' && (
          loading ? <LoadingSpinner /> : stats && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem' }}>
              <StatCard label="Total Jobs" value={stats.total_jobs} color="var(--color-primary)" />
              <StatCard label="Open" value={stats.open_jobs} color="var(--color-success)" />
              <StatCard label="Completed" value={stats.completed_jobs} color="var(--color-accent)" />
              <StatCard label="Avg Rating Given" value={stats.avg_rating_given?.toFixed(1) || '—'} color="var(--color-warning)" />
            </div>
          )
        )}

        {view === 'post' && (
          <div style={{ maxWidth: '600px' }}>
            <h3 style={{ marginBottom: '1rem' }}>Post a New Job</h3>
            <div className="card">
              <JobPostForm onSuccess={() => { setView('jobs'); loadData() }} />
            </div>
          </div>
        )}

        {view === 'jobs' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <h3>My Jobs</h3>
            {loading ? <LoadingSpinner /> : jobs.map((job) => (
              <div key={job.id} className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.5rem' }}>
                  <div>
                    <div style={{ fontWeight: 700 }}>{job.title}</div>
                    <div style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>
                      {job.profession_required} · {formatCurrency(job.budget_min, job.currency)}–{formatCurrency(job.budget_max, job.currency)} · Due: {formatDate(job.deadline)}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <span style={{ background: STATUS_COLORS[job.status] || '#ccc', color: '#fff', padding: '0.2em 0.7em', borderRadius: '99px', fontSize: '0.8rem', textTransform: 'capitalize' }}>
                      {job.status}
                    </span>
                    {job.status === 'draft' && (
                      <button onClick={() => handlePublish(job.id)} className="btn-primary" style={{ fontSize: '0.85rem', padding: '0.3rem 0.7rem' }}>
                        Publish
                      </button>
                    )}
                    {['matched', 'open'].includes(job.status) && (
                      <button onClick={() => setSelectedJob(selectedJob?.id === job.id ? null : job)} className="btn-outline" style={{ fontSize: '0.85rem', padding: '0.3rem 0.7rem' }}>
                        {selectedJob?.id === job.id ? 'Hide' : 'Matches'}
                      </button>
                    )}
                  </div>
                </div>
                {selectedJob?.id === job.id && (
                  <div style={{ marginTop: '1rem', borderTop: '1px solid var(--color-border)', paddingTop: '1rem' }}>
                    <h4 style={{ marginBottom: '0.75rem' }}>Matched Professionals</h4>
                    <MatchedProfessionals jobId={job.id} />
                    {job.status === 'matched' && (
                      <div style={{ marginTop: '1rem' }}>
                        <EscrowFundWidget jobId={job.id} />
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )
}
