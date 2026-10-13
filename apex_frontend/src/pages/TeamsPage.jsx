import { useState } from 'react'
import Navbar from '../components/common/Navbar'
import toast from 'react-hot-toast'

const consortiums = [
  { name: 'Manufacturing Consortium', skills: 'Robotics · Mechanical · AI · Electrical · Safety', merit: '94.8', deployments: 187, tone: '#f97316' },
  { name: 'Digital Operations Collective', skills: 'Software · Data · Automation · Product', merit: '91.2', deployments: 124, tone: '#38bdf8' },
  { name: 'Built Environment Network', skills: 'Construction · Logistics · Safety · Energy', merit: '88.6', deployments: 96, tone: '#4ade80' },
]

export default function TeamsPage() {
  const [teamName, setTeamName] = useState('')
  const [teams, setTeams] = useState([])

  const createTeam = () => {
    if (!teamName.trim()) return
    setTeams((current) => [...current, { name: teamName.trim(), members: 1, merit: '—' }])
    setTeamName('')
    toast.success('Team created. You can invite verified members next.')
  }

  return (
    <>
      <Navbar />
      <main className="page-container" style={{ maxWidth: '1180px' }}>
        <section style={{ padding: '2.5rem 0 2rem', borderBottom: '1px solid var(--color-border)' }}>
          <div style={{ color: '#fb923c', fontSize: '0.75rem', letterSpacing: '0.16em', fontWeight: 800 }}>COORDINATED CAPABILITY</div>
          <h1 style={{ fontSize: 'clamp(2rem, 5vw, 4rem)', maxWidth: '760px', margin: '0.5rem 0 0.8rem' }}>Teams that make larger work possible.</h1>
          <p style={{ maxWidth: '680px', color: 'var(--color-text-muted)', fontSize: '1.05rem' }}>Verified Business Nodes and enterprise workforces combine their capabilities for serious deployments under clear MSA agreements.</p>
        </section>

        <section style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(280px, 0.72fr)', gap: '1.5rem', padding: '2rem 0' }}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
              <div><div style={{ color: 'var(--color-text-muted)', fontSize: '0.78rem', textTransform: 'uppercase' }}>Workspace</div><h2>My Teams</h2></div>
              <span style={{ color: 'var(--color-text-muted)' }}>{teams.length} active</span>
            </div>
            <div className="card" style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap', marginBottom: '0.8rem' }}>
              <input aria-label="Team name" placeholder="Name your team" value={teamName} onChange={(e) => setTeamName(e.target.value)} style={{ flex: 1, minWidth: '180px' }} />
              <button className="btn-primary" onClick={createTeam}>Create Team</button>
            </div>
            {teams.length === 0 && <div className="card" style={{ color: 'var(--color-text-muted)' }}>Create a focused team, then invite verified members with the capability coverage your next deployment needs.</div>}
            {teams.map((team) => <div className="card" key={team.name} style={{ marginBottom: '0.7rem', display: 'flex', justifyContent: 'space-between' }}><div><strong>{team.name}</strong><div style={{ color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>{team.members} member · Invite members · Add capability</div></div><strong>{team.merit}</strong></div>)}
          </div>
          <aside style={{ borderLeft: '3px solid #fb923c', paddingLeft: '1rem' }}>
            <div style={{ color: 'var(--color-text-muted)', fontSize: '0.78rem', textTransform: 'uppercase' }}>Enterprise Consortium</div>
            <h3 style={{ margin: '0.5rem 0' }}>Keep the workforce. Expand the capability.</h3>
            <p style={{ color: 'var(--color-text-muted)', lineHeight: 1.6 }}>Apex assembles existing employees from approved enterprise partners instead of replacing them with strangers.</p>
            <ul style={{ color: 'var(--color-text-muted)', lineHeight: 1.8, paddingLeft: '1.2rem' }}><li>Company retains its workforce</li><li>Employees gain capability</li><li>Company gains deployment intelligence</li><li>Better future opportunities</li></ul>
          </aside>
        </section>

        <section style={{ padding: '1rem 0 3rem' }}>
          <div style={{ marginBottom: '1rem' }}><div style={{ color: 'var(--color-text-muted)', fontSize: '0.78rem', textTransform: 'uppercase' }}>Verified by industry</div><h2>Consortium Marketplace</h2></div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '0.8rem' }}>
            {consortiums.map((item) => <article className="card" key={item.name} style={{ borderTop: `3px solid ${item.tone}` }}><h3>{item.name}</h3><p style={{ color: 'var(--color-text-muted)', minHeight: '48px' }}>{item.skills}</p><div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid var(--color-border)', paddingTop: '0.8rem' }}><span>Merit <strong>{item.merit}</strong></span><span>{item.deployments} deployments</span></div></article>)}
          </div>
        </section>
      </main>
    </>
  )
}
