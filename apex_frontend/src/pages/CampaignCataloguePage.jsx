import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api, { getErrorMessage, unwrapList } from '../api/client'
import Page from '../components/Page'
import { Empty, ErrorState, Loading, PaginationControls } from '../components/States'
import { useAuth } from '../context/AuthContext'
import './VendorManagementPage.css'

export default function CampaignCataloguePage() {
  const { user } = useAuth()
  const [campaigns, setCampaigns] = useState([])
  const [status, setStatus] = useState({ loading: true, error: '' })
  const [trackingError, setTrackingError] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)

  const load = useCallback(() => {
    setStatus({ loading: true, error: '' })
    api.get('/campaigns/active/', { params: { page } })
      .then(({ data }) => { setCampaigns(unwrapList(data)); setTotal(data?.count ?? 0); setStatus({ loading: false, error: '' }) })
      .catch((error) => setStatus({ loading: false, error: getErrorMessage(error) }))
  }, [page])

  useEffect(() => { load() }, [load])

  const followCampaign = async (campaign) => {
    setTrackingError('')
    try {
      await api.post(`/campaigns/${campaign.id}/events/`, { event_type: 'click' })
    } catch (error) {
      if (error.response?.status !== 401 && error.response?.status !== 403) setTrackingError(getErrorMessage(error))
    }
  }

  return <Page eyebrow="SPONSORED LEARNING" title="Campaign catalogue" description="Active sponsorships are labelled with their sponsor. Sponsorship does not influence assessment answers, scores, or merit.">
    {trackingError && <div className="alert alert-error" role="alert">{trackingError}</div>}
    {status.loading ? <Loading label="Loading active sponsorships…" /> : status.error ? <ErrorState message={status.error} retry={load} /> : campaigns.length === 0 ? <Empty title="No active sponsorships">Approved campaigns will appear here during their scheduled dates.</Empty> : <><div className="content-grid">{campaigns.map((campaign) => <article className="panel vendor-public-campaign" key={campaign.id}>
      <span className="tag">Sponsored · {campaign.campaign_type.replaceAll('_', ' ')}</span>
      <h2>{campaign.name}</h2><p>{campaign.description}</p>
      <p><strong>Objectives:</strong> {campaign.objectives}</p>
      <p><strong>Study area:</strong> {campaign.study_area || 'Learning initiative'}</p>
      <p className="vendor-campaign-disclosure">{campaign.sponsor_disclosure}</p>
      {Object.keys(campaign.eligibility_rules || {}).length > 0 && <p><strong>Sponsor-proposed participation information:</strong> <code>{JSON.stringify(campaign.eligibility_rules)}</code><br /><small>Informational only; it does not change assessment access, scoring, merit, or awards.</small></p>}
      <small>Campaign dates: {campaign.start_date} – {campaign.end_date}</small>
      <Link className="button button-quiet" to={user ? (campaign.study_area ? `/study/${encodeURIComponent(campaign.study_area)}` : '/study') : '/login'} onClick={() => user && followCampaign(campaign)}>{user ? 'Explore learning ↗' : 'Sign in to explore learning ↗'}</Link>
    </article>)}</div><PaginationControls page={page} total={total} onPageChange={setPage} /></>}
  </Page>
}
