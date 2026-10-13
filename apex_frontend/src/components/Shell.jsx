import { NavLink, Link, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { mobileNavItems, navItems } from '../data'

export default function Shell() {
  const { user, logout } = useAuth()
  const location = useLocation()
  const title = navItems.find((item) => location.pathname === item.to || (item.to !== '/dashboard' && location.pathname.startsWith(item.to)))?.label || 'Your Apex'
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link to="/dashboard" className="brand"><span className="brand-symbol">A</span><span>APEXSTRATOS<small>PROVE · PERFORM · PROGRESS</small></span></Link>
        <div className="side-label">WORKSPACE</div>
        <nav className="side-nav">
          {navItems.map((item) => <NavLink key={item.to} to={item.to} end={item.to === '/dashboard'} className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}><span className="nav-icon">{item.icon}</span>{item.label}</NavLink>)}
        </nav>
        <div className="side-bottom">
          <NavLink to="/notifications" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}><span className="nav-icon">◉</span>Notifications</NavLink>
          {user?.is_admin && <NavLink to="/admin" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}><span className="nav-icon">⌘</span>Admin tools</NavLink>}
          <div className="user-mini"><div className="avatar">{(user?.username || user?.email || 'A')[0].toUpperCase()}</div><div className="user-meta"><strong>{user?.username || 'Apex learner'}</strong><span>{user?.role || 'student'}</span></div><button className="icon-button" title="Sign out" onClick={logout}>↗</button></div>
        </div>
      </aside>
      <main className="main-area">
        <header className="topbar"><div className="crumb">APEXSTRATOS <span>/</span> {title.toUpperCase()}</div><div className="top-actions"><span className="live-dot" /> <span className="secure-label">YOUR SPACE</span><Link className="top-avatar" to="/profile" aria-label="Your profile">{(user?.username || 'A')[0].toUpperCase()}</Link><button className="icon-button mobile-signout" title="Sign out" aria-label="Sign out" onClick={logout}>↗</button></div></header>
        <div className="mobile-brand"><Link to="/dashboard" className="brand"><span className="brand-symbol">A</span><span>APEXSTRATOS</span></Link><Link to="/notifications" className="icon-button" aria-label="Notifications">◉</Link></div>
        <nav className="mobile-nav" aria-label="Student navigation">{mobileNavItems.map((item) => <NavLink key={item.to} to={item.to} aria-label={item.label} title={item.label}><span aria-hidden="true">{item.icon}</span><small>{item.label}</small></NavLink>)}</nav>
        <div className="content"><Outlet /></div>
      </main>
    </div>
  )
}
