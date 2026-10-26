import { useCallback, useEffect, useState } from 'react'
import api, { getErrorMessage, unwrapList } from '../api/client'
import { Empty, Loading, PaginationControls } from '../components/States'
import './VendorManagementPage.css'

export default function AdminVendorManagement() {
  const [tab, setTab] = useState('vendors')
  const [vendorStatus, setVendorStatus] = useState('pending')
  const [campaignStatus, setCampaignStatus] = useState('pending_approval')
  const [vendorPage, setVendorPage] = useState(1)
  const [campaignPage, setCampaignPage] = useState(1)
  const [vendorTotal, setVendorTotal] = useState(0)
  const [campaignTotal, setCampaignTotal] = useState(0)
  const [vendors, setVendors] = useState([])
  const [campaigns, setCampaigns] = useState([])
  const [busy, setBusy] = useState('')
  const [feedback, setFeedback] = useState({})
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      if (tab === 'vendors') {
        const { data } = await api.get('/admin/vendors/', { params: { status: vendorStatus, page: vendorPage } })
        setVendors(unwrapList(data))
        setVendorTotal(data?.count ?? 0)
      } else {
        const { data } = await api.get('/admin/vendors/campaigns/', { params: { ...(campaignStatus ? { status: campaignStatus } : {}), page: campaignPage } })
        setCampaigns(unwrapList(data))
        setCampaignTotal(data?.count ?? 0)
      }
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }, [campaignPage, campaignStatus, tab, vendorPage, vendorStatus])

  useEffect(() => { load() }, [load])

  const vendorDecision = async (vendor, decision) => {
    setBusy(vendor.id)
    setError('')
    try {
      await api.post(`/admin/vendors/${vendor.id}/decision/`, {
        status: decision,
        feedback: feedback[vendor.id] || '',
      })
      await load()
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setBusy('')
    }
  }

  const verificationDecision = async (verification, decision) => {
    setBusy(verification.id)
    setError('')
    try {
      await api.post(`/admin/vendors/verifications/${verification.id}/decision/`, {
        status: decision,
        feedback: feedback[verification.id] || '',
      })
      await load()
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setBusy('')
    }
  }

  const downloadDocument = async (verification) => {
    setBusy(verification.id)
    setError('')
    try {
      const { data } = await api.get(`/admin/vendors/verifications/${verification.id}/document/`, { responseType: 'blob' })
      const url = URL.createObjectURL(data)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${verification.document_type.replace(/[^a-z0-9_-]/gi, '-')}-${verification.id}`
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setBusy('')
    }
  }

  const campaignDecision = async (campaign, decision) => {
    setBusy(campaign.id)
    setError('')
    try {
      await api.post(`/admin/vendors/campaigns/${campaign.id}/decision/`, {
        decision,
        feedback: feedback[campaign.id] || '',
      })
      await load()
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setBusy('')
    }
  }

  const tabs = ['vendors', 'campaigns']
  return <section className="admin-vendor-panel">
    <div className="vendor-tabs" role="tablist" aria-label="Vendor administration">
      {tabs.map((value) => <button className={`button ${tab === value ? 'button-primary' : 'button-quiet'}`} type="button" role="tab" aria-selected={tab === value} key={value} onClick={() => setTab(value)}>{value === 'vendors' ? 'Vendor applications' : 'Campaign proposals'}</button>)}
    </div>
    <div className="panel admin-vendor-controls">
      <label>Status<select value={tab === 'vendors' ? vendorStatus : campaignStatus} onChange={(event) => { if (tab === 'vendors') { setVendorStatus(event.target.value); setVendorPage(1) } else { setCampaignStatus(event.target.value); setCampaignPage(1) } }}>
        {(tab === 'vendors' ? ['pending', 'approved', 'rejected', 'suspended'] : ['', 'draft', 'pending_approval', 'changes_requested', 'approved', 'active', 'paused', 'cancellation_requested', 'completed', 'rejected', 'cancelled']).map((value) => <option key={value || 'all'} value={value}>{value ? value.replaceAll('_', ' ') : 'All statuses'}</option>)}
      </select></label>
      <button className="button button-quiet" type="button" disabled={loading} onClick={load}>Refresh</button>
    </div>
    {error && <div className="alert alert-error" role="alert">{error}</div>}
    {loading ? <Loading label="Loading vendor administration…" /> : tab === 'vendors' ? vendors.length === 0 ? <Empty title="No vendor profiles match this status" /> : <div className="admin-vendor-list">{vendors.map((vendor) => <article className="panel admin-vendor-card" key={vendor.id}>
      <div className="panel-heading"><div><h2>{vendor.business_name}</h2><span>{vendor.email} · {vendor.category} · {vendor.location}</span></div><span className={`tag status-${vendor.status}`}>{vendor.status}</span></div>
      <p>{vendor.description}</p><p><strong>Contact:</strong> {vendor.contact_name} · {vendor.contact_email} · {vendor.contact_phone}</p>
      <label>Administrative feedback<textarea rows={2} maxLength={5000} value={feedback[vendor.id] ?? vendor.admin_feedback ?? ''} onChange={(event) => setFeedback((current) => ({ ...current, [vendor.id]: event.target.value }))} /></label>
      <h3>Verification documents</h3>
      {(vendor.verifications || []).length ? vendor.verifications.map((verification) => <div className="admin-vendor-verification" key={verification.id}><strong>{verification.document_type}</strong><span className={`tag status-${verification.status}`}>{verification.status}</span><button className="button button-quiet" disabled={busy === verification.id || !verification.has_document} onClick={() => downloadDocument(verification)}>Download securely</button><label>Review feedback<textarea rows={1} maxLength={5000} value={feedback[verification.id] ?? verification.admin_feedback ?? ''} onChange={(event) => setFeedback((current) => ({ ...current, [verification.id]: event.target.value }))} /></label>{verification.status === 'pending' && <><button className="button button-quiet" disabled={busy === verification.id} onClick={() => verificationDecision(verification, 'approved')}>Approve document</button><button className="button button-quiet" disabled={busy === verification.id} onClick={() => verificationDecision(verification, 'rejected')}>Reject document</button></>}</div>) : <p>No verification documents submitted.</p>}
      <div className="vendor-campaign-actions">{vendor.status !== 'approved' && vendor.status !== 'suspended' && <button className="button button-primary" disabled={busy === vendor.id} onClick={() => vendorDecision(vendor, 'approved')}>Approve vendor</button>}{vendor.status === 'pending' && <button className="button button-quiet" disabled={busy === vendor.id} onClick={() => vendorDecision(vendor, 'rejected')}>Reject vendor</button>}{vendor.status === 'approved' && <button className="button button-quiet" disabled={busy === vendor.id} onClick={() => vendorDecision(vendor, 'suspended')}>Suspend vendor</button>}{vendor.status === 'suspended' && <button className="button button-primary" disabled={busy === vendor.id} onClick={() => vendorDecision(vendor, 'reactivated')}>Reactivate vendor</button>}</div>
    </article>)}</div> : campaigns.length === 0 ? <Empty title="No campaign proposals match this status" /> : <div className="admin-vendor-list">{campaigns.map((campaign) => <article className="panel admin-vendor-card" key={campaign.id}>
      <div className="panel-heading"><div><h2>{campaign.name}</h2><span>{campaign.vendor_name} · {campaign.campaign_type.replaceAll('_', ' ')} · {campaign.study_area || 'All areas'}</span></div><span className={`tag status-${campaign.status}`}>{campaign.status.replaceAll('_', ' ')}</span></div>
      <p>{campaign.description}</p><p><strong>Objectives:</strong> {campaign.objectives}</p><p><strong>Audience:</strong> {campaign.target_audience}</p><p className="vendor-campaign-disclosure"><strong>Disclosure:</strong> {campaign.sponsor_disclosure}</p><p><strong>Dates:</strong> {campaign.start_date} – {campaign.end_date} · Proposed budget {campaign.currency} {campaign.budget_amount ?? 'not provided'}</p>
      {Object.keys(campaign.eligibility_rules || {}).length > 0 && <p><strong>Proposed participation rules (review before approval):</strong> <code>{JSON.stringify(campaign.eligibility_rules)}</code></p>}
      <div className="admin-vendor-assets">{(campaign.assets || []).map((asset) => <a key={asset.id} href={asset.file} target="_blank" rel="noreferrer">{asset.description || 'Campaign asset'}</a>)}</div>
      <label>Decision feedback<textarea rows={2} maxLength={5000} value={feedback[campaign.id] ?? campaign.admin_feedback ?? ''} onChange={(event) => setFeedback((current) => ({ ...current, [campaign.id]: event.target.value }))} /></label>
      {campaign.status === 'pending_approval' && <><p className="soft-label">Budget figures are proposals only. Billing and spending tracking are not configured.</p><div className="vendor-campaign-actions"><button className="button button-primary" disabled={busy === campaign.id} onClick={() => campaignDecision(campaign, 'approve')}>Approve campaign</button><button className="button button-quiet" disabled={busy === campaign.id} onClick={() => campaignDecision(campaign, 'changes_requested')}>Request changes</button><button className="button button-quiet" disabled={busy === campaign.id} onClick={() => campaignDecision(campaign, 'reject')}>Reject campaign</button></div></>}
      {campaign.status === 'approved' && <button className="button button-primary" disabled={busy === campaign.id} onClick={() => campaignDecision(campaign, 'activate')}>Activate during scheduled dates</button>}
      {campaign.status === 'paused' && <button className="button button-primary" disabled={busy === campaign.id} onClick={() => campaignDecision(campaign, 'resume')}>Resume campaign</button>}
      {campaign.status === 'cancellation_requested' && <div className="vendor-campaign-actions"><button className="button button-primary" disabled={busy === campaign.id} onClick={() => campaignDecision(campaign, 'confirm_cancellation')}>Confirm cancellation</button><button className="button button-quiet" disabled={busy === campaign.id} onClick={() => campaignDecision(campaign, 'deny_cancellation')}>Deny cancellation</button></div>}
      {campaign.review_history?.length > 0 && <details><summary>Review history</summary><ol>{campaign.review_history.map((record, index) => <li key={`${record.decision}-${record.created_at}-${index}`}>{record.decision.replaceAll('_', ' ')} · {record.actor_email || 'System'} · {new Date(record.created_at).toLocaleString()}{record.feedback && ` — ${record.feedback}`}</li>)}</ol></details>}
    </article>)}</div>}
    {!loading && !error && tab === 'vendors' && vendors.length > 0 && <PaginationControls page={vendorPage} total={vendorTotal} onPageChange={setVendorPage} />}
    {!loading && !error && tab === 'campaigns' && campaigns.length > 0 && <PaginationControls page={campaignPage} total={campaignTotal} onPageChange={setCampaignPage} />}
  </section>
}
