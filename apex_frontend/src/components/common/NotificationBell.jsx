import { useNavigate } from 'react-router-dom'
import { useNotifications } from '../../context/NotificationContext'

export default function NotificationBell() {
  const { unreadCount } = useNotifications()
  const navigate = useNavigate()

  return (
    <button
      onClick={() => navigate('/notifications')}
      style={{ position: 'relative', background: 'none', padding: '0.5rem' }}
      aria-label="Notifications"
    >
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
        <path d="M13.73 21a2 2 0 0 1-3.46 0" />
      </svg>
      {unreadCount > 0 && (
        <span style={{
          position: 'absolute', top: 0, right: 0,
          background: 'var(--color-error)', color: '#fff',
          borderRadius: '99px', fontSize: '0.7rem', fontWeight: 700,
          padding: '0 0.35em', minWidth: '1.2em', textAlign: 'center',
        }}>
          {unreadCount > 99 ? '99+' : unreadCount}
        </span>
      )}
    </button>
  )
}
