export function Loading({ label = 'Loading from Apex…' }) {
  return <div className="state"><span className="spinner" />{label}</div>
}

export function Empty({ title = 'Nothing here yet', children }) {
  return <div className="state empty-state"><span className="empty-mark">—</span><strong>{title}</strong><span>{children || 'When there is something to show, it will appear here.'}</span></div>
}

export function ErrorState({ message, retry }) {
  return <div className="state error-state"><strong>Could not load this data</strong><span>{message}</span>{retry && <button className="button button-quiet" onClick={retry}>Try again</button>}</div>
}

export function Unavailable({ title, children }) {
  return <div className="state unavailable"><span className="eyebrow">NOT CONNECTED</span><strong>{title}</strong><span>{children}</span></div>
}
