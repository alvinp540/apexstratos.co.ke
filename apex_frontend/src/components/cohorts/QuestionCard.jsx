export default function QuestionCard({ question, index, selected, onSelect, disabled = false }) {
  return (
    <div className="card" style={{ marginBottom: '1rem' }}>
      <div style={{ fontWeight: 600, marginBottom: '0.75rem' }}>
        Q{index + 1}. {question.text}
        <span style={{ marginLeft: '0.5rem', color: 'var(--color-text-muted)', fontSize: '0.8rem' }}>
          ({question.points} pt{question.points !== 1 ? 's' : ''})
        </span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {question.options.map((opt) => (
          <label key={opt.id} style={{
            display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer',
            padding: '0.5rem', borderRadius: 'calc(var(--radius)/2)',
            background: selected === opt.id ? 'var(--color-primary)' : 'var(--color-bg)',
            color: selected === opt.id ? '#fff' : 'var(--color-text)',
            border: `1.5px solid ${selected === opt.id ? 'var(--color-primary)' : 'var(--color-border)'}`,
          }}>
            <input
              type="radio" name={`q_${question.id}`} value={opt.id}
              checked={String(selected) === String(opt.id)}
              disabled={disabled}
              onChange={() => onSelect(String(question.id), opt.id)}
              style={{ display: 'none' }}
            />
            {opt.text}
          </label>
        ))}
      </div>
    </div>
  )
}
