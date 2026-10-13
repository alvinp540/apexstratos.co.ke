import { useState } from 'react'
import Navbar from '../components/common/Navbar'

const communities = [
  { name: 'AI Engineering', members: '1,284', activity: '12 new discussions', color: '#a78bfa', topics: 'Expert discussions · Weekly challenges · Capability news' },
  { name: 'Construction & Safety', members: '864', activity: '6 active case studies', color: '#f59e0b', topics: 'Mentor sessions · Case studies · Industry opportunities' },
  { name: 'Robotics & Manufacturing', members: '642', activity: '4 consortiums forming', color: '#22c55e', topics: 'Emerging technologies · Challenges · Consortium formation' },
  { name: 'Software Development', members: '2,106', activity: '18 mentor sessions', color: '#38bdf8', topics: 'Expert discussions · Mentor sessions · Capability news' },
  { name: 'Healthcare Operations', members: '438', activity: '3 new opportunities', color: '#fb7185', topics: 'Case studies · Industry opportunities · Weekly challenges' },
  { name: 'Agriculture & Logistics', members: '377', activity: '8 new discussions', color: '#84cc16', topics: 'Capability news · Emerging technologies · Expert discussions' },
]

export default function CommunitiesPage() {
  const [query, setQuery] = useState('')
  const filtered = communities.filter((community) => community.name.toLowerCase().includes(query.toLowerCase()))
  return (
    <>
      <Navbar />
      <main className="page-container" style={{ maxWidth: '1180px' }}>
        <section style={{ padding: '2.5rem 0 2rem', borderBottom: '1px solid var(--color-border)' }}>
          <div style={{ color: '#22c55e', fontSize: '0.75rem', letterSpacing: '0.16em', fontWeight: 800 }}>CAPABILITY NETWORK</div>
          <h1 style={{ fontSize: 'clamp(2rem, 5vw, 4rem)', maxWidth: '760px', margin: '0.5rem 0 0.8rem' }}>Communities for work that keeps getting better.</h1>
          <p style={{ maxWidth: '680px', color: 'var(--color-text-muted)', fontSize: '1.05rem' }}>Not social media. Professional spaces where Business Nodes learn, collaborate, and discuss real-world problems.</p>
        </section>
        <section style={{ padding: '2rem 0 3rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'end', gap: '1rem', flexWrap: 'wrap', marginBottom: '1rem' }}><div><div style={{ color: 'var(--color-text-muted)', fontSize: '0.78rem', textTransform: 'uppercase' }}>Explore by capability</div><h2>Communities</h2></div><input aria-label="Search communities" placeholder="Search communities" value={query} onChange={(e) => setQuery(e.target.value)} style={{ maxWidth: '240px' }} /></div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '0.8rem' }}>
            {filtered.map((community) => <article className="card" key={community.name} style={{ borderLeft: `4px solid ${community.color}`, minHeight: '170px' }}><div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem' }}><h3>{community.name}</h3><span style={{ color: community.color }}>●</span></div><p style={{ color: 'var(--color-text-muted)', lineHeight: 1.5 }}>{community.topics}</p><div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--color-text-muted)', fontSize: '0.85rem', marginTop: '1rem' }}><span>{community.members} nodes</span><span>{community.activity}</span></div></article>)}
          </div>
        </section>
      </main>
    </>
  )
}
