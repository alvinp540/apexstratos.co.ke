import { useEffect, useState } from 'react'
import Navbar from '../components/common/Navbar'
import MeritScoreWidget from '../components/dashboard/MeritScoreWidget'
import AvailabilityToggle from '../components/dashboard/AvailabilityToggle'
import OpportunityFeed from '../components/dashboard/OpportunityFeed'
import ProgressAnalytics from '../components/dashboard/ProgressAnalytics'
import { useAuth } from '../context/AuthContext'
import { getMyProfile } from '../api/profileAPI'
import { getMyRanking } from '../api/rankingAPI'
import { getProfessionalAnalytics } from '../api/analyticsAPI'
import api from '../api/axiosInstance'
import SocialFeed from '../components/dashboard/SocialFeed'

export default function DashboardPage() {
  const { user } = useAuth()
  const [dashboardData, setDashboardData] = useState(null)

  useEffect(() => {
    Promise.all([
      getMyProfile(),
      getMyRanking(),
      getProfessionalAnalytics(),
      api.get('/trust/score/'),
      api.get('/trust/score/history/'),
    ]).then(([profile, ranking, analytics, score, history]) => {
      setDashboardData({ profile: profile.data, ranking: ranking.data, analytics: analytics.data, score: score.data, history: history.data })
    }).catch(() => {})

    // fetch up to 6 daily available cohorts
    import('../api/cohortAPI').then(({ getDailyCohorts }) => {
      getDailyCohorts().then(({ data }) => setDailyCohorts(data || [])).catch(() => setDailyCohorts([]))
    })
  }, [])

  const profile = dashboardData?.profile
  const analytics = dashboardData?.analytics
  const score = dashboardData?.score
  const ranking = dashboardData?.ranking
  const history = dashboardData?.history || []
  const displayName = profile?.full_name || user?.username || 'there'
  const displayRole = profile?.profession || profile?.headline || 'Professional'
  const scoreDelta = score && history.length > 1 ? score.overall_merit_score - history[history.length - 2].overall_merit_score : 0
  const scoreTrend = history.length > 1 ? history.map((item) => Number(item.overall_merit_score || 0)) : []

  const statCards = [
    { label: 'Assessments', value: analytics?.total_assessments ?? '—' },
    { label: 'Global Rank', value: ranking?.global_rank ? `#${ranking.global_rank}` : '—' },
    { label: 'Jobs Completed', value: analytics?.jobs_completed ?? '—' },
    { label: 'Average Score', value: analytics ? `${Number(analytics.avg_score || 0).toFixed(1)}%` : '—' },
  ]
  const [dailyCohorts, setDailyCohorts] = useState([])

  const metricCards = [
    { title: 'Merit Score', value: score ? Number(score.overall_merit_score).toFixed(0) : '—', delta: scoreDelta >= 0 ? `+${scoreDelta.toFixed(0)}` : scoreDelta.toFixed(0), color: '#8b5cf6' },
    { title: 'Average Assessment', value: analytics ? `${Number(analytics.avg_score || 0).toFixed(1)}%` : '—', delta: analytics ? `${analytics.total_assessments} taken` : '—', color: '#22c55e' },
    { title: 'Opportunities', value: analytics?.opportunities_received ?? '—', delta: analytics ? `${analytics.flagged_attempts} flagged` : '—', color: '#f59e0b' },
    { title: 'Vendor Rating', value: analytics ? `${Number(analytics.avg_vendor_rating || 0).toFixed(1)}` : '—', delta: 'live', color: '#06b6d4' },
  ]

  const bars = scoreTrend.length > 1 ? scoreTrend : [0]

  return (
    <>
      <Navbar />
      <div className="page-container" style={{ maxWidth: '1280px', paddingTop: '2.5rem' }}>
        <div style={{ maxWidth: '760px', marginBottom: '2rem' }}><SocialFeed /></div>
        <div style={{ display: 'grid', gridTemplateColumns: '1.7fr 0.9fr', gap: '1.5rem', marginBottom: '2rem' }}>
          <div style={{ background: 'rgba(15,23,42,0.82)', border: '1px solid rgba(148,163,184,0.12)', borderRadius: '1.3rem', padding: '1.4rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <div>
                <div style={{ fontSize: '0.72rem', letterSpacing: '0.14em', color: '#a78bfa', textTransform: 'uppercase', fontWeight: 700 }}>Cohort assessment</div>
                <h2 style={{ marginTop: '0.35rem', fontSize: '2.1rem', fontWeight: 800 }}>Welcome back, {displayName}</h2>
              </div>
              <div style={{ background: 'rgba(139,92,246,0.14)', border: '1px solid rgba(139,92,246,0.22)', color: '#ddd6fe', padding: '0.5rem 0.85rem', borderRadius: '999px', fontWeight: 700, fontSize: '0.78rem' }}>Live score</div>
            </div>

            <div style={{ background: 'linear-gradient(135deg, rgba(17,24,39,0.9), rgba(15,23,42,0.8))', borderRadius: '1rem', padding: '1rem', border: '1px solid rgba(255,255,255,0.06)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
                <div style={{ width: '54px', height: '54px', borderRadius: '50%', background: 'linear-gradient(135deg, #c4b5fd, #8b5cf6)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, color: '#fff' }}>{displayName.slice(0, 2).toUpperCase()}</div>
                <div>
                  <div style={{ fontWeight: 800, fontSize: '1.25rem' }}>{displayName}</div>
                  <div style={{ color: '#94a3b8', fontSize: '0.8rem' }}>{displayRole}</div>
                </div>
              </div>

              <div style={{ marginBottom: '0.7rem', color: '#94a3b8', fontSize: '0.78rem' }}>Merit Score</div>
              <div style={{ fontSize: '2.5rem', fontWeight: 900, letterSpacing: '-0.06em', marginBottom: '0.8rem' }}>{score ? Number(score.overall_merit_score).toFixed(0) : '—'} <span style={{ fontSize: '1rem', color: scoreDelta >= 0 ? '#4ade80' : '#fb7185', marginLeft: '0.5rem' }}>{dashboardData ? `${scoreDelta >= 0 ? '↑' : '↓'} ${Math.abs(scoreDelta).toFixed(0)}` : 'Loading'}</span></div>

              {dailyCohorts.length > 0 && (
                <div style={{ marginTop: '0.6rem', padding: '0.8rem', background: 'rgba(255,255,255,0.02)', borderRadius: '0.8rem' }}>
                  <div style={{ fontWeight: 800, marginBottom: '0.45rem' }}>Today's recommended cohorts</div>
                  {dailyCohorts.slice(0, 6).map((c) => (
                    <div key={c.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.45rem 0' }}>
                      <div style={{ fontSize: '0.9rem' }}>{c.title} <div style={{ color: '#94a3b8', fontSize: '0.75rem' }}>{c.profession}</div></div>
                      <div>
                        <button onClick={async () => {
                          try {
                            const { data } = await import('../api/cohortAPI').then(m => m.startAssessment(c.assessments?.[0]?.id || c.default_assessment_id))
                            window.location.href = `/cohorts?start=${data.id}`
                          } catch (err) {
                            console.error(err)
                            toast.error(err.response?.data?.error || 'Could not start cohort.')
                          }
                        }} className="btn-primary">Start</button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <div style={{ display: 'flex', alignItems: 'flex-end', height: '72px', gap: '0.35rem', marginBottom: '1rem' }}>
                {bars.map((value, index) => (
                  <div key={index} style={{ flex: 1, height: `${scoreTrend.length > 1 ? Math.max(8, (value / Math.max(...scoreTrend)) * 100) : 8}%`, borderRadius: '0.35rem 0.35rem 0 0', background: index % 2 === 0 ? 'linear-gradient(180deg, #a78bfa, #7c3aed)' : 'linear-gradient(180deg, #4f46e5, #7c3aed)' }} />
                ))}
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0,1fr))', gap: '0.75rem' }}>
                {statCards.map((item) => (
                  <div key={item.label} style={{ background: 'rgba(15,23,42,0.7)', border: '1px solid rgba(148,163,184,0.1)', borderRadius: '0.8rem', padding: '0.8rem' }}>
                    <div style={{ color: '#94a3b8', fontSize: '0.7rem', marginBottom: '0.25rem' }}>{item.label}</div>
                    <div style={{ fontSize: '1.6rem', fontWeight: 800 }}>{item.value}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div style={{ background: 'rgba(15,23,42,0.82)', border: '1px solid rgba(148,163,184,0.12)', borderRadius: '1.3rem', padding: '1.2rem' }}>
            <div style={{ fontSize: '0.72rem', letterSpacing: '0.14em', textTransform: 'uppercase', color: '#a78bfa', fontWeight: 700, marginBottom: '0.75rem' }}>Insights</div>
            <div style={{ background: 'linear-gradient(135deg, rgba(139,92,246,0.12), rgba(14,165,233,0.08))', border: '1px solid rgba(167,139,250,0.15)', borderRadius: '1rem', padding: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.8rem' }}>
                <div style={{ fontWeight: 700 }}>Performance trend</div>
                <span style={{ color: '#4ade80', fontWeight: 700 }}>+12.4%</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: '0.35rem', height: '120px' }}>
                {(scoreTrend.length > 1 ? scoreTrend : [0]).map((value, index, values) => (
                  <div key={index} style={{ flex: 1, height: `${values.length > 1 ? Math.max(8, (value / Math.max(...values)) * 100) : 8}%`, borderRadius: '0.42rem 0.42rem 0 0', background: index % 2 === 0 ? 'linear-gradient(180deg, #c4b5fd, #8b5cf6)' : 'linear-gradient(180deg, #7c3aed, #4f46e5)' }} />
                ))}
              </div>
            </div>
            <div style={{ marginTop: '1rem', color: '#cbd5e1', lineHeight: 1.7, fontSize: '0.9rem' }}>{dashboardData ? `Your live merit score is ${Number(score.overall_merit_score).toFixed(0)}${scoreDelta ? `, ${scoreDelta > 0 ? 'up' : 'down'} ${Math.abs(scoreDelta).toFixed(0)} from the previous record` : ''}.` : 'Loading your live performance and improvement data.'}</div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem' }}>
          <div>
            <MeritScoreWidget />
            <div style={{ marginTop: '1rem' }}>
              <AvailabilityToggle />
            </div>
          </div>
          <OpportunityFeed />
        </div>

        <div style={{ marginTop: '2rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem' }}>
            {metricCards.map((card) => (
              <div key={card.title} style={{ background: 'rgba(15,23,42,0.82)', border: '1px solid rgba(148,163,184,0.12)', borderRadius: '1rem', padding: '1.2rem 1rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: '0.4rem' }}>{card.title}</div>
                  <div style={{ fontSize: '1.9rem', fontWeight: 800 }}>{card.value}</div>
                </div>
                <div style={{ background: 'rgba(8, 145, 178, 0.12)', color: card.color, borderRadius: '999px', padding: '0.35rem 0.6rem', fontWeight: 700, fontSize: '0.75rem' }}>{card.delta}</div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ marginTop: '2rem' }}>
          <ProgressAnalytics />
        </div>
      </div>
    </>
  )
}
