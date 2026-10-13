import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { useTheme } from '../../context/ThemeContext'
import NotificationBell from './NotificationBell'
import { logout as logoutApi } from '../../api/authAPI'
import { sendPresence } from '../../api/profileAPI'
import { useEffect } from 'react'

export default function Navbar() {
  const { user, logout } = useAuth()
  const { dark, toggle } = useTheme()
  const navigate = useNavigate()

  useEffect(() => {
    if (!user) return undefined
    const syncPresence = () => sendPresence(document.visibilityState === 'visible' && navigator.onLine).catch(() => {})
    syncPresence()
    const timer = window.setInterval(syncPresence, 30000)
    window.addEventListener('online', syncPresence)
    window.addEventListener('offline', syncPresence)
    document.addEventListener('visibilitychange', syncPresence)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('online', syncPresence)
      window.removeEventListener('offline', syncPresence)
      document.removeEventListener('visibilitychange', syncPresence)
      sendPresence(false).catch(() => {})
    }
  }, [user])

  const handleLogout = async () => {
    try {
      await logoutApi(localStorage.getItem('refresh_token'))
    } catch {}
    logout()
    navigate('/login')
  }

  return (
    <nav style={{
      position: 'sticky', top: 0, zIndex: 100,
      background: 'rgba(5, 13, 26, 0.9)',
      backdropFilter: 'blur(14px)',
      borderBottom: '1px solid rgba(148, 163, 184, 0.12)',
      padding: '0 1.5rem',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      height: '72px', boxShadow: '0 8px 20px rgba(2, 6, 23, 0.12)',
    }}>
      <Link to="/" style={{ fontWeight: 900, fontSize: '1.5rem', color: '#f3e8ff', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '0.55rem' }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: '26px', height: '26px', borderRadius: '8px', background: 'linear-gradient(135deg, #8b5cf6, #7c3aed)', fontSize: '0.9rem' }}>A</span>
        APEX 1.0
      </Link>

      {!user && (
        <div style={{ display: 'flex', gap: '1.7rem', alignItems: 'center', color: '#dbeafe' }}>
          <Link to="/" style={{ color: '#dbeafe', fontWeight: 600, opacity: 0.92 }}>Home</Link>
          <Link to="/cohorts" style={{ color: '#dbeafe', fontWeight: 600, opacity: 0.92 }}>Cohorts</Link>
          <Link to="/opportunities" style={{ color: '#dbeafe', fontWeight: 600, opacity: 0.92 }}>Opportunities</Link>
          <Link to="/rankings" style={{ color: '#dbeafe', fontWeight: 600, opacity: 0.92 }}>Leaderboard</Link>
          <a href="#resources" style={{ color: '#dbeafe', fontWeight: 600, opacity: 0.92 }}>Resources</a>
        </div>
      )}

      {user && (
        <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center' }}>
          <Link to="/dashboard" style={{ color: '#dbeafe', textDecoration: 'none', fontWeight: 600 }}>Dashboard</Link>
          <Link to="/mentors" style={{ color: '#dbeafe', textDecoration: 'none', fontWeight: 600 }}>Mentors</Link>
          <Link to="/teams" style={{ color: '#dbeafe', textDecoration: 'none', fontWeight: 600 }}>Teams</Link>
          <Link to="/communities" style={{ color: '#dbeafe', textDecoration: 'none', fontWeight: 600 }}>Communities</Link>
          <Link to="/cohorts" style={{ color: '#dbeafe', textDecoration: 'none', fontWeight: 600 }}>Cohorts</Link>
          <Link to="/opportunities" style={{ color: '#dbeafe', textDecoration: 'none', fontWeight: 600 }}>Opportunities</Link>
          <Link to="/rankings" style={{ color: '#dbeafe', textDecoration: 'none', fontWeight: 600 }}>Leaderboard</Link>
          {user.role === 'vendor' && <Link to="/vendor" style={{ color: '#dbeafe', textDecoration: 'none', fontWeight: 600 }}>Vendor</Link>}
          {user.is_admin === true && <Link to="/admin" style={{ color: '#dbeafe', textDecoration: 'none', fontWeight: 600 }}>Admin</Link>}
        </div>
      )}

      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
        <button onClick={toggle} style={{ background: 'transparent', padding: '0.45rem', border: '1px solid rgba(148, 163, 184, 0.18)', borderRadius: '0.65rem', color: '#dbeafe', fontSize: '1rem' }}>
          {dark ? '☀️' : '🌙'}
        </button>

        {user ? (
          <>
            <NotificationBell />
            <Link to="/profile" style={{ fontWeight: 700, color: '#dbeafe', textDecoration: 'none' }}>{user.username}</Link>
            <button onClick={handleLogout} className="btn-outline" style={{ padding: '0.5rem 0.9rem' }}>
              Logout
            </button>
          </>
        ) : (
          <>
            <select style={{ background: 'transparent', border: '1px solid rgba(148, 163, 184, 0.18)', color: '#dbeafe', borderRadius: '0.6rem', padding: '0.45rem 0.7rem', fontWeight: 600 }}>
              <option>EN</option>
              <option>FR</option>
              <option>SW</option>
            </select>
            <Link to="/login"><button style={{ background: 'transparent', color: '#dbeafe', border: '1px solid rgba(148, 163, 184, 0.2)', borderRadius: '0.7rem', padding: '0.55rem 1rem', fontWeight: 700 }}>Login</button></Link>
            <Link to="/register"><button className="btn-primary" style={{ padding: '0.6rem 1.2rem', fontWeight: 800 }}>Join Apex</button></Link>
          </>
        )}
      </div>
    </nav>
  )
}
