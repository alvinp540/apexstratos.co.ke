import { useState, useEffect } from 'react'
import Navbar from '../components/common/Navbar'
import { getNotifications, markRead, markAllRead } from '../api/notificationAPI'
import { useNotifications } from '../context/NotificationContext'
import { formatTimeAgo } from '../utils/formatters'
import LoadingSpinner from '../components/common/LoadingSpinner'
import toast from 'react-hot-toast'

const TYPE_ICONS = {
  opportunity: '🚀', ranking_change: '📈', score_update: '⭐',
  payment: '💰', assessment: '📝', system: '🔔',
}

export default function NotificationsPage() {
  const [notifications, setNotifications] = useState([])
  const [loading, setLoading] = useState(true)
  const { refreshCount } = useNotifications()

  useEffect(() => {
    getNotifications().then(({ data }) => setNotifications(data.results || data)).catch(() => {}).finally(() => setLoading(false))
  }, [])

  const handleRead = async (id) => {
    await markRead(id)
    setNotifications((n) => n.map((notif) => notif.id === id ? { ...notif, is_read: true } : notif))
    refreshCount()
  }

  const handleReadAll = async () => {
    await markAllRead()
    setNotifications((n) => n.map((notif) => ({ ...notif, is_read: true })))
    refreshCount()
    toast.success('All marked as read.')
  }

  return (
    <>
      <Navbar />
      <div className="page-container">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <h2>Notifications</h2>
          <button onClick={handleReadAll} className="btn-outline">Mark all read</button>
        </div>
        {loading ? <LoadingSpinner /> : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {notifications.length === 0 && <p style={{ color: 'var(--color-text-muted)' }}>No notifications yet.</p>}
            {notifications.map((n) => (
              <div key={n.id} onClick={() => !n.is_read && handleRead(n.id)} className="card" style={{
                display: 'flex', gap: '1rem', cursor: n.is_read ? 'default' : 'pointer',
                opacity: n.is_read ? 0.7 : 1,
                borderLeft: n.is_read ? '4px solid var(--color-border)' : '4px solid var(--color-primary)',
              }}>
                <span style={{ fontSize: '1.5rem' }}>{TYPE_ICONS[n.notification_type] || '🔔'}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600 }}>{n.title}</div>
                  <div style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>{n.message}</div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>{formatTimeAgo(n.created_at)}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )
}
