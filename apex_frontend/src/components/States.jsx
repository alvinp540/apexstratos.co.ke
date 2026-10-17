export function Loading({ label = 'Loading from Apex…' }) {
  return <div className="state"><span className="spinner" />{label}</div>
}

export function Empty({ title = 'Nothing here yet', children }) {
  return <div className="state empty-state"><span className="empty-mark">—</span><strong>{title}</strong><span>{children || 'When there is something to show, it will appear here.'}</span></div>
}

export function ErrorState({ message, retry }) {
  return <div className="state error-state"><strong>Could not load this data</strong><span>{message}</span>{retry && <button className="button button-quiet" onClick={retry}>Try again</button>}</div>
}

export function PaginationControls({ page, pageSize = 20, total, onPageChange }) {
  const pageCount = Math.ceil(total / pageSize)
  if (pageCount <= 1) return null
  return <nav className="filter-row" aria-label="Assessment library pages">
    <button className="button button-quiet" type="button" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>Previous page</button>
    <span aria-live="polite">Page {page} of {pageCount} · {total} assessments</span>
    <button className="button button-quiet" type="button" disabled={page >= pageCount} onClick={() => onPageChange(page + 1)}>Next page</button>
  </nav>
}

export function Unavailable({ title, children }) {
  return <div className="state unavailable"><span className="eyebrow">NOT CONNECTED</span><strong>{title}</strong><span>{children}</span></div>
}
