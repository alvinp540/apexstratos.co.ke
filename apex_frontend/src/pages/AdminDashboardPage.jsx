import { useState } from 'react'
import Navbar from '../components/common/Navbar'
import UserManagementTable from '../components/admin/UserManagementTable'
import FraudMonitorPanel from '../components/admin/FraudMonitorPanel'
import PlatformAnalyticsChart from '../components/admin/PlatformAnalyticsChart'
import MentorsTab from '../components/admin/MentorsTab'
import PSPRegistrations from '../components/admin/PSPRegistrations'
import RewardsPanel from '../components/admin/RewardsPanel'
import api from '../api/axiosInstance'
import toast from 'react-hot-toast'

export default function AdminDashboardPage() {
  const [tab, setTab] = useState('analytics')

  const handleRecalculate = async () => {
    try {
      await api.post('/admin/rankings/recalculate/')
      toast.success('Ranking recalculation started.')
    } catch { toast.error('Failed.') }
  }

  const TABS = ['analytics', 'users', 'fraud', 'mentors', 'psp', 'rewards']

  return (
    <>
      <Navbar />
      <div className="page-container">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '0.75rem' }}>
          <h2>Admin Dashboard</h2>
          <button onClick={handleRecalculate} className="btn-outline">Recalculate All Rankings</button>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
          {TABS.map((t) => (
            <button key={t} onClick={() => setTab(t)} style={{
              background: tab === t ? 'var(--color-primary)' : 'var(--color-border)',
              color: tab === t ? '#fff' : 'var(--color-text)',
              textTransform: 'capitalize',
            }}>
              {t === 'analytics' ? 'Platform Analytics' : t === 'users' ? 'User Management' : t === 'fraud' ? 'Fraud Monitor' : t === 'mentors' ? 'Mentors' : t === 'psp' ? 'PSP Registrations' : 'Rewards & Payouts'}
            </button>
          ))}
        </div>

        {tab === 'analytics' && <PlatformAnalyticsChart />}
        {tab === 'users' && <UserManagementTable />}
        {tab === 'fraud' && <FraudMonitorPanel />}
        {tab === 'mentors' && <MentorsTab />}
        {tab === 'psp' && <PSPRegistrations />}
        {tab === 'rewards' && <RewardsPanel />}
      </div>
    </>
  )
}
