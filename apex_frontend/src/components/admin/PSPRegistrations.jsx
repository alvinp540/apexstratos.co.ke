import { useCallback, useEffect, useState } from 'react'
import api from '../../api/pspAPI'
import toast from 'react-hot-toast'

export default function PSPRegistrations() {
  const [registrations, setRegistrations] = useState([])
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(false)
  const [verifyPayload, setVerifyPayload] = useState({ amount_received: '', payment_reference: '', notes: '' })

  const fetch = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.listPSPRegistrations({ q: query })
      setRegistrations(data)
    } catch (e) { console.error(e); toast.error('Failed to fetch') }
    setLoading(false)
  }, [query])

  useEffect(() => { fetch() }, [fetch])

  const open = async (reg) => {
    try {
      const full = await api.getPSPRegistration(reg.id)
      setSelected(full)
    } catch (e) { console.error(e); toast.error('Failed to load') }
  }

  const handleVerify = async () => {
    if (!selected) return
    try {
      const payload = { amount_received: verifyPayload.amount_received, payment_reference: verifyPayload.payment_reference, notes: verifyPayload.notes }
      await api.verifyPSPRegistration(selected.id, payload)
      toast.success('Verification recorded')
      setSelected(null)
      fetch()
    } catch (e) { console.error(e); toast.error('Failed to verify') }
  }

  return (
    <div style={{ display: 'flex', gap: '1rem' }}>
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
          <input placeholder="Search name or phone" value={query} onChange={(e) => setQuery(e.target.value)} />
          <button onClick={fetch} className="btn-outline">Search</button>
        </div>

        <h4>PSP Registrations (Till 1598106)</h4>
        {loading && <div>Loading...</div>}
        {!loading && registrations.length === 0 && <div>No registrations found.</div>}
        {!loading && registrations.map((r) => (
          <div key={r.id} style={{ padding: '0.75rem', border: '1px solid var(--color-border)', borderRadius: '6px', marginBottom: '0.5rem', display: 'flex', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontWeight: 700 }}>{r.full_name}</div>
              <div style={{ fontSize: '0.9rem', color: 'var(--color-muted)' }}>{r.phone_number} • {r.psp_tier} • {r.status}</div>
            </div>
            <div>
              <button onClick={() => open(r)} className="btn-outline">View</button>
            </div>
          </div>
        ))}
      </div>

      <aside style={{ width: 420, padding: '0.75rem', border: '1px solid var(--color-border)', borderRadius: '6px' }}>
        {!selected && <div>Select a registration to view details</div>}
        {selected && (
          <div>
            <h4>{selected.full_name}</h4>
            <div>Phone: {selected.phone_number}</div>
            <div>Tier: {selected.psp_tier}</div>
            <div>Amount expected: {selected.amount_expected}</div>
            <div>Status: {selected.status}</div>

            <h5 style={{ marginTop: '0.75rem' }}>Verifications</h5>
            {selected.verifications.length === 0 && <div>No verifications</div>}
            {selected.verifications.map((v) => (
              <div key={v.id} style={{ padding: '0.35rem 0', borderBottom: '1px solid rgba(0,0,0,0.04)' }}>
                <div><strong>{v.amount_received}</strong> — {v.payment_reference}</div>
                <div style={{ fontSize: '0.85rem', color: 'var(--color-muted)' }}>{new Date(v.verified_at).toLocaleString()} by {v.verified_by?.username}</div>
              </div>
            ))}

            <h5 style={{ marginTop: '0.75rem' }}>Verify Payment (manual)</h5>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <input placeholder="Amount received" value={verifyPayload.amount_received} onChange={(e) => setVerifyPayload(p => ({ ...p, amount_received: e.target.value }))} />
              <input placeholder="Payment reference" value={verifyPayload.payment_reference} onChange={(e) => setVerifyPayload(p => ({ ...p, payment_reference: e.target.value }))} />
              <textarea placeholder="Notes" value={verifyPayload.notes} onChange={(e) => setVerifyPayload(p => ({ ...p, notes: e.target.value }))} />
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button onClick={handleVerify} className="btn-primary">Verify Payment</button>
                <button onClick={() => setSelected(null)} className="btn-outline">Close</button>
              </div>
            </div>
          </div>
        )}
      </aside>
    </div>
  )
}
