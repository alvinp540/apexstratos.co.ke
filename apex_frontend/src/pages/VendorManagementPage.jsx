import { useCallback, useEffect, useState } from 'react'
import api, { getErrorMessage, unwrapList } from '../api/client'
import Page from '../components/Page'
import { Empty, ErrorState, Loading, PaginationControls } from '../components/States'
import { studyAreas } from '../data'
import './VendorManagementPage.css'

const EMPTY_PROFILE = {
  business_name: '',
  description: '',
  category: 'education',
  contact_name: '',
  contact_email: '',
  contact_phone: '',
  website: '',
  location: '',
}

const EMPTY_CAMPAIGN = {
  name: '',
  objectives: '',
  target_audience: '',
  eligibility_rules: '{}',
  campaign_type: 'tutorial',
  study_area: '',
  target_content_ids: '',
  description: '',
  sponsor_disclosure: '',
  start_date: '',
  end_date: '',
  target_views: '',
  budget_amount: '',
  currency: 'KES',
}
const EDITABLE_CAMPAIGN_STATUSES = ['draft', 'rejected', 'changes_requested']

export default function VendorManagementPage() {
  const [profile, setProfile] = useState(null)
  const [dashboard, setDashboard] = useState(null)
  const [campaigns, setCampaigns] = useState([])
  const [campaignPage, setCampaignPage] = useState(1)
  const [campaignsTotal, setCampaignsTotal] = useState(0)
  const [selected, setSelected] = useState(null)
  const [report, setReport] = useState(null)
  const [profileForm, setProfileForm] = useState(EMPTY_PROFILE)
  const [logoFile, setLogoFile] = useState(null)
  const [campaignForm, setCampaignForm] = useState(EMPTY_CAMPAIGN)
  const [documentForm, setDocumentForm] = useState({ document_type: '', document: null })
  const [busy, setBusy] = useState('')
  const [status, setStatus] = useState({ loading: true, error: '' })
  const [notice, setNotice] = useState({ error: '', success: '' })
  const [tab, setTab] = useState('overview')

  const load = useCallback(async () => {
    setStatus({ loading: true, error: '' })
    try {
      const [profileResponse, dashboardResponse] = await Promise.allSettled([
        api.get('/vendors/profile/'),
        api.get('/vendors/dashboard/'),
      ])
      if (profileResponse.status === 'rejected' && profileResponse.reason?.response?.status !== 404) {
        throw profileResponse.reason
      }
      if (profileResponse.status === 'fulfilled') {
        setProfile(profileResponse.value.data)
        setProfileForm(Object.fromEntries(Object.keys(EMPTY_PROFILE).map((key) => [key, profileResponse.value.data[key] ?? ''])))
      } else {
        setProfile(null)
      }
      if (dashboardResponse.status === 'fulfilled') setDashboard(dashboardResponse.value.data)
      else if (dashboardResponse.reason?.response?.status !== 403) throw dashboardResponse.reason

      if (profileResponse.status === 'fulfilled' && profileResponse.value.data.status === 'approved') {
        const { data } = await api.get('/campaigns/', { params: { page: campaignPage } })
        setCampaigns(unwrapList(data))
        setCampaignsTotal(data?.count ?? 0)
      } else {
        setCampaigns([])
        setCampaignsTotal(0)
      }
      setStatus({ loading: false, error: '' })
    } catch (error) {
      setStatus({ loading: false, error: getErrorMessage(error) })
    }
  }, [campaignPage])

  useEffect(() => { load() }, [load])

  const selectCampaign = async (campaign) => {
    setSelected(campaign)
    setReport(null)
    setNotice({ error: '', success: '' })
    if (campaign.status === 'active' || campaign.status === 'paused' || campaign.status === 'completed') {
      try {
        const { data } = await api.get(`/campaigns/${campaign.id}/report/`)
        setReport(data)
      } catch (error) {
        setNotice({ error: getErrorMessage(error), success: '' })
      }
    }
  }

  const saveProfile = async (event) => {
    event.preventDefault()
    setBusy('profile')
    setNotice({ error: '', success: '' })
    try {
      const method = profile ? 'patch' : 'post'
      const formData = new FormData()
      Object.entries(profileForm).forEach(([key, value]) => formData.append(key, value))
      if (logoFile) formData.append('logo', logoFile)
      const { data } = await api[method]('/vendors/onboarding/', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
      setProfile(data)
      setLogoFile(null)
      setNotice({ error: '', success: 'Vendor application saved. It must be approved before campaigns can be managed.' })
      await load()
    } catch (error) {
      setNotice({ error: getErrorMessage(error), success: '' })
    } finally {
      setBusy('')
    }
  }

  const submitVerification = async (event) => {
    event.preventDefault()
    if (!documentForm.document) return
    const formData = new FormData()
    formData.append('document_type', documentForm.document_type)
    formData.append('document', documentForm.document)
    setBusy('verification')
    setNotice({ error: '', success: '' })
    try {
      await api.post('/vendors/verifications/', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
      setDocumentForm({ document_type: '', document: null })
      setNotice({ error: '', success: 'Verification document submitted for administrative review.' })
      await load()
    } catch (error) {
      setNotice({ error: getErrorMessage(error), success: '' })
    } finally {
      setBusy('')
    }
  }

  const saveCampaign = async (event) => {
    event.preventDefault()
    let eligibilityRules
    try {
      eligibilityRules = JSON.parse(campaignForm.eligibility_rules || '{}')
    } catch {
      setNotice({ error: 'Eligibility rules must be valid JSON.', success: '' })
      return
    }
    if (!eligibilityRules || Array.isArray(eligibilityRules) || typeof eligibilityRules !== 'object') {
      setNotice({ error: 'Eligibility rules must be a JSON object.', success: '' })
      return
    }
    setBusy('campaign')
    setNotice({ error: '', success: '' })
    try {
      const payload = {
        ...campaignForm,
        eligibility_rules: eligibilityRules,
        target_content_ids: campaignForm.target_content_ids.split(',').map((value) => value.trim()).filter(Boolean),
        target_views: campaignForm.target_views || null,
        budget_amount: campaignForm.budget_amount || null,
      }
      const isEditing = selected && EDITABLE_CAMPAIGN_STATUSES.includes(selected.status)
      const { data } = isEditing
        ? await api.patch(`/campaigns/${selected.id}/`, payload)
        : await api.post('/campaigns/', payload)
      setCampaigns((current) => isEditing
        ? current.map((campaign) => campaign.id === data.id ? data : campaign)
        : [data, ...current])
      if (!isEditing) {
        setCampaignPage(1)
        setCampaignsTotal((current) => current + 1)
      }
      setSelected(data)
      setCampaignForm(EMPTY_CAMPAIGN)
      setNotice({ error: '', success: isEditing ? 'Campaign draft updated. Submit it when it is ready for review.' : 'Campaign saved as a draft. Submit it when it is ready for review.' })
      setTab('campaigns')
      const { data: dashboardData } = await api.get('/vendors/dashboard/')
      setDashboard(dashboardData)
    } catch (error) {
      setNotice({ error: getErrorMessage(error), success: '' })
    } finally {
      setBusy('')
    }
  }

  const campaignAction = async (url, payload, successMessage) => {
    if (!selected) return
    setBusy('action')
    setNotice({ error: '', success: '' })
    try {
      const { data } = await api.post(url(selected.id), payload)
      if (data.id === selected.id) {
        setSelected(data)
        setCampaigns((current) => current.map((item) => item.id === data.id ? data : item))
      } else {
        const { data: updated } = await api.get(`/campaigns/${selected.id}/`)
        setSelected(updated)
        setCampaigns((current) => current.map((item) => item.id === updated.id ? updated : item))
      }
      setNotice({ error: '', success: successMessage })
      await load()
    } catch (error) {
      setNotice({ error: getErrorMessage(error), success: '' })
    } finally {
      setBusy('')
    }
  }

  const downloadReport = async () => {
    if (!selected) return
    setBusy('report')
    setNotice({ error: '', success: '' })
    try {
      const { data } = await api.get(`/campaigns/${selected.id}/report.csv`, { responseType: 'blob' })
      const url = URL.createObjectURL(data)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `campaign-${selected.id}-report.csv`
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (error) {
      setNotice({ error: getErrorMessage(error), success: '' })
    } finally {
      setBusy('')
    }
  }

  const editCampaign = (campaign) => {
    setSelected(campaign)
    setCampaignForm({
      name: campaign.name,
      objectives: campaign.objectives,
      target_audience: campaign.target_audience,
      eligibility_rules: JSON.stringify(campaign.eligibility_rules || {}, null, 2),
      campaign_type: campaign.campaign_type,
      study_area: campaign.study_area || '',
      target_content_ids: (campaign.target_content_ids || []).join(', '),
      description: campaign.description,
      sponsor_disclosure: campaign.sponsor_disclosure,
      start_date: campaign.start_date,
      end_date: campaign.end_date,
      target_views: campaign.target_views ?? '',
      budget_amount: campaign.budget_amount ?? '',
      currency: campaign.currency,
    })
    setTab('new_campaign')
  }

  if (status.loading) return <Page eyebrow="VENDOR PORTAL" title="Vendor and sponsorship management"><Loading /></Page>
  if (status.error) return <Page eyebrow="VENDOR PORTAL" title="Vendor and sponsorship management"><ErrorState message={status.error} retry={load} /></Page>

  const campaignCounts = dashboard?.campaigns_by_status || {}

  return <Page eyebrow="VENDOR PORTAL" title="Vendor and sponsorship management" description="Complete onboarding, submit disclosed sponsorship proposals, and track campaigns after approval.">
    <div className="vendor-tabs" role="tablist" aria-label="Vendor workspace">
      {['overview', 'profile', ...(profile?.status === 'approved' ? ['campaigns', 'new_campaign'] : [])].map((value) => <button key={value} className={`button ${tab === value ? 'button-primary' : 'button-quiet'}`} type="button" role="tab" aria-selected={tab === value} onClick={() => { if (value === 'new_campaign') { setSelected(null); setCampaignForm(EMPTY_CAMPAIGN) } setTab(value) }}>{value === 'new_campaign' ? 'Propose campaign' : value.replace('_', ' ')}</button>)}
    </div>
    {notice.error && <div className="alert alert-error" role="alert">{notice.error}</div>}
    {notice.success && <div className="alert alert-success" role="status">{notice.success}</div>}

    {tab === 'overview' && <section className="vendor-overview">
      {!profile ? <div className="panel vendor-callout"><h2>Start vendor onboarding</h2><p>Submit your organization profile. You will be able to propose campaigns after an administrator reviews and approves it.</p><button className="button button-primary" onClick={() => setTab('profile')}>Complete vendor profile</button></div> : <>
        <div className="panel vendor-profile-status"><div><span className="eyebrow">VENDOR STATUS</span>{profile.logo && <img className="vendor-profile-logo" src={profile.logo} alt={`${profile.business_name} logo`} />}<h2>{profile.business_name}</h2><span className={`tag status-${profile.status}`}>{profile.status.replace('_', ' ')}</span><p>{profile.admin_feedback || 'Profile and verification decisions appear here.'}</p></div><div><strong>{profile.category}</strong><span>{profile.location}</span><span>{profile.contact_email}</span></div></div>
        {profile.status !== 'approved' && <div className="panel"><h2>Verification documents</h2><p>Documents are visible only to you and authorized administrators.</p><form className="vendor-form vendor-document-form" onSubmit={submitVerification}><label>Document type<input required maxLength={64} value={documentForm.document_type} onChange={(event) => setDocumentForm((current) => ({ ...current, document_type: event.target.value }))} /></label><label>Document (PDF or image, up to 10 MB)<input required type="file" accept="application/pdf,image/jpeg,image/png,image/webp" onChange={(event) => setDocumentForm((current) => ({ ...current, document: event.target.files?.[0] || null }))} /></label><button className="button button-quiet" disabled={busy === 'verification'}>{busy === 'verification' ? 'Uploading…' : 'Submit verification document'}</button></form>
          <ul className="vendor-verification-list">{(profile.verifications || []).map((item) => <li key={item.id}><strong>{item.document_type}</strong><span className={`tag status-${item.status}`}>{item.status}</span>{item.admin_feedback && <p>{item.admin_feedback}</p>}</li>)}</ul>
        </div>}
        {profile.status === 'approved' && <><div className="vendor-stat-grid">{Object.entries(campaignCounts).map(([key, value]) => <div className="panel vendor-stat" key={key}><span>{key.replaceAll('_', ' ')}</span><strong>{value}</strong></div>)}</div><div className="panel vendor-billing-note"><strong>Billing and spending reports are disabled.</strong><span>No sponsorship payment provider is configured; proposed/approved budgets do not represent payments or spend.</span></div></>}
      </>}
    </section>}

    {tab === 'profile' && <section className="panel"><h2>{profile ? 'Vendor profile' : 'Vendor onboarding application'}</h2><form className="vendor-form" onSubmit={saveProfile}>
      <label>Business name<input required maxLength={200} value={profileForm.business_name} onChange={(event) => setProfileForm((current) => ({ ...current, business_name: event.target.value }))} /></label>
      <label>Category<select value={profileForm.category} onChange={(event) => setProfileForm((current) => ({ ...current, category: event.target.value }))}>{['education', 'technology', 'health', 'finance', 'engineering', 'media', 'other'].map((value) => <option key={value} value={value}>{value.replace('_', ' ')}</option>)}</select></label>
      <label>Contact name<input required maxLength={150} value={profileForm.contact_name} onChange={(event) => setProfileForm((current) => ({ ...current, contact_name: event.target.value }))} /></label>
      <label>Contact email<input required type="email" value={profileForm.contact_email} onChange={(event) => setProfileForm((current) => ({ ...current, contact_email: event.target.value }))} /></label>
      <label>Contact phone<input required maxLength={32} value={profileForm.contact_phone} onChange={(event) => setProfileForm((current) => ({ ...current, contact_phone: event.target.value }))} /></label>
      <label>Website <span className="optional">optional</span><input type="url" value={profileForm.website} onChange={(event) => setProfileForm((current) => ({ ...current, website: event.target.value }))} /></label>
      <label>Location<input required maxLength={200} value={profileForm.location} onChange={(event) => setProfileForm((current) => ({ ...current, location: event.target.value }))} /></label>
      <label>Business logo <span className="optional">optional, image up to 5 MB</span><input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setLogoFile(event.target.files?.[0] || null)} /></label>
      <label className="vendor-form-wide">Business description<textarea required rows={4} value={profileForm.description} onChange={(event) => setProfileForm((current) => ({ ...current, description: event.target.value }))} /></label>
      <button className="button button-primary" disabled={busy === 'profile'}>{busy === 'profile' ? 'Saving…' : profile ? 'Update vendor application' : 'Submit vendor application'}</button>
    </form></section>}

    {tab === 'new_campaign' && <section className="panel"><h2>{selected && EDITABLE_CAMPAIGN_STATUSES.includes(selected.status) ? 'Edit campaign draft' : 'Campaign proposal'}</h2><p>Proposals cannot go live without administrator approval. Do not include claims that imply control over assessment answers or merit.</p><form className="vendor-form" onSubmit={saveCampaign}>
      <label>Campaign name<input required maxLength={200} value={campaignForm.name} onChange={(event) => setCampaignForm((current) => ({ ...current, name: event.target.value }))} /></label>
      <label>Campaign type<select value={campaignForm.campaign_type} onChange={(event) => setCampaignForm((current) => ({ ...current, campaign_type: event.target.value }))}>{[['tutorial', 'Tutorial sponsorship'], ['study_area', 'Study area'], ['learning_initiative', 'Learning initiative'], ['contest', 'Contest sponsorship'], ['support_program', 'Support programme']].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>Study area<select value={campaignForm.study_area} onChange={(event) => setCampaignForm((current) => ({ ...current, study_area: event.target.value }))}><option value="">All / not specified</option>{studyAreas.map((area) => <option key={area}>{area}</option>)}</select></label>
      <label>Target {campaignForm.campaign_type === 'contest' ? 'contest assessment' : 'tutorial'} IDs <span className="optional">optional, comma-separated</span><input value={campaignForm.target_content_ids} onChange={(event) => setCampaignForm((current) => ({ ...current, target_content_ids: event.target.value }))} /></label>
      <label>Target audience<input required maxLength={500} value={campaignForm.target_audience} onChange={(event) => setCampaignForm((current) => ({ ...current, target_audience: event.target.value }))} /></label>
      <label className="vendor-form-wide">Proposed participation / eligibility rules <span className="optional">optional JSON; platform assessment/merit rules are not overridden</span><textarea rows={3} maxLength={5000} value={campaignForm.eligibility_rules} onChange={(event) => setCampaignForm((current) => ({ ...current, eligibility_rules: event.target.value }))} placeholder='{"regions":["Kenya"],"minimum_age":18}' /></label>
      <label>Start date<input required type="date" value={campaignForm.start_date} onChange={(event) => setCampaignForm((current) => ({ ...current, start_date: event.target.value }))} /></label>
      <label>End date<input required type="date" value={campaignForm.end_date} onChange={(event) => setCampaignForm((current) => ({ ...current, end_date: event.target.value }))} /></label>
      <label>Target views <span className="optional">optional</span><input min="0" type="number" value={campaignForm.target_views} onChange={(event) => setCampaignForm((current) => ({ ...current, target_views: event.target.value }))} /></label>
      <label>Proposed budget (KES) <span className="optional">optional; not a payment</span><input min="0" step="0.01" type="number" value={campaignForm.budget_amount} onChange={(event) => setCampaignForm((current) => ({ ...current, budget_amount: event.target.value }))} /></label>
      <label className="vendor-form-wide">Objectives<textarea required rows={3} value={campaignForm.objectives} onChange={(event) => setCampaignForm((current) => ({ ...current, objectives: event.target.value }))} /></label>
      <label className="vendor-form-wide">Campaign description<textarea required rows={4} value={campaignForm.description} onChange={(event) => setCampaignForm((current) => ({ ...current, description: event.target.value }))} /></label>
      <label className="vendor-form-wide">Sponsor disclosure shown to learners<textarea required rows={2} placeholder="Sponsored by [organization]." value={campaignForm.sponsor_disclosure} onChange={(event) => setCampaignForm((current) => ({ ...current, sponsor_disclosure: event.target.value }))} /></label>
      <button className="button button-primary" disabled={busy === 'campaign'}>{busy === 'campaign' ? 'Saving…' : selected && EDITABLE_CAMPAIGN_STATUSES.includes(selected.status) ? 'Update campaign draft' : 'Save campaign draft'}</button>
    </form></section>}

    {tab === 'campaigns' && <section className="vendor-campaign-layout">
      <section className="panel vendor-campaign-list"><div className="panel-heading"><h2>My campaigns</h2><button className="button button-quiet" onClick={load}>Refresh</button></div>{campaigns.length ? <>{campaigns.map((item) => <button className={`vendor-campaign-row${selected?.id === item.id ? ' selected' : ''}`} key={item.id} onClick={() => selectCampaign(item)}><strong>{item.name}</strong><span>{item.campaign_type.replaceAll('_', ' ')}</span><span className={`tag status-${item.status}`}>{item.status.replaceAll('_', ' ')}</span></button>)}<PaginationControls page={campaignPage} total={campaignsTotal} onPageChange={setCampaignPage} /></> : <Empty title="No campaign proposals">Create a draft proposal to begin.</Empty>}</section>
      {selected && <article className="panel vendor-campaign-detail"><div className="panel-heading"><h2>{selected.name}</h2><span className={`tag status-${selected.status}`}>{selected.status.replaceAll('_', ' ')}</span></div><p>{selected.description}</p><p><strong>Objectives:</strong> {selected.objectives}</p><p><strong>Dates:</strong> {selected.start_date} – {selected.end_date}</p><p><strong>Disclosure:</strong> {selected.sponsor_disclosure}</p>
        {selected.admin_feedback && <div className="alert alert-error"><strong>Administrator feedback</strong><p>{selected.admin_feedback}</p></div>}
        {EDITABLE_CAMPAIGN_STATUSES.includes(selected.status) ? <><button className="button button-quiet" type="button" onClick={() => editCampaign(selected)}>Edit draft</button><form className="vendor-document-form" onSubmit={async (event) => { event.preventDefault(); const formData = new FormData(); formData.append('description', event.currentTarget.description.value); formData.append('file', event.currentTarget.file.files[0]); await campaignAction((id) => `/campaigns/${id}/assets/`, formData, 'Campaign asset uploaded.'); event.currentTarget.reset() }}><label>Creative asset (PDF or image, up to 15 MB)<input name="file" required type="file" accept="application/pdf,image/jpeg,image/png,image/webp" /></label><label>Asset description<input name="description" maxLength={300} /></label><button className="button button-quiet" type="submit" disabled={busy === 'action'}>Upload asset</button></form><ul>{(selected.assets || []).map((asset) => <li key={asset.id}><a href={asset.file} target="_blank" rel="noreferrer">{asset.description || 'Campaign asset'}</a></li>)}</ul><button className="button button-primary" disabled={busy === 'action'} onClick={() => campaignAction((id) => `/campaigns/${id}/submit/`, {}, 'Campaign submitted for administrator review.')}>Submit for approval</button></> : null}
        {selected.review_history?.length > 0 && <details><summary>Campaign review history</summary><ol>{selected.review_history.map((record, index) => <li key={`${record.decision}-${record.created_at}-${index}`}>{record.decision.replaceAll('_', ' ')} · {new Date(record.created_at).toLocaleString()}{record.feedback && ` — ${record.feedback}`}</li>)}</ol></details>}
        {selected.status === 'active' && <div className="vendor-campaign-actions"><button className="button button-quiet" disabled={busy === 'action'} onClick={() => campaignAction((id) => `/campaigns/${id}/actions/`, { action: 'pause' }, 'Campaign paused.')}>Pause campaign</button><button className="button button-quiet" disabled={busy === 'action'} onClick={() => campaignAction((id) => `/campaigns/${id}/actions/`, { action: 'request_cancellation' }, 'Cancellation request submitted.')}>Request cancellation</button></div>}
        {selected.status === 'paused' && <button className="button button-quiet" disabled={busy === 'action'} onClick={() => campaignAction((id) => `/campaigns/${id}/actions/`, { action: 'request_cancellation' }, 'Cancellation request submitted.')}>Request cancellation</button>}
        {report && <section className="vendor-report"><div className="panel-heading"><h3>Campaign report</h3><button className="button button-quiet" disabled={busy === 'report'} onClick={downloadReport}>Export CSV</button></div>{report.suppressed ? <p>{report.suppression_note}</p> : <><p>{report.metric_disclaimer}</p><div className="vendor-report-grid">{Object.entries(report).filter(([key]) => (key.startsWith('recorded_') && key !== 'recorded_activity_by_day') || key.endsWith('_rate')).map(([key, value]) => <div key={key}><span>{key.replaceAll('_', ' ')}</span><strong>{key.endsWith('_rate') ? `${(value * 100).toFixed(1)}%` : value}</strong></div>)}</div>{report.recorded_activity_by_day?.length > 0 && <div className="vendor-report-trends"><h4>Daily recorded activity (minimum audience threshold applied per day and event)</h4><div className="vendor-report-grid">{report.recorded_activity_by_day.map((entry) => <div key={`${entry.date}-${entry.event_type}`}><span>{entry.date} · {entry.event_type.replaceAll('_', ' ')}</span><strong>{entry.count}</strong></div>)}</div></div>}</>}</section>}
      </article>}
    </section>}
  </Page>
}
