export default function Page({ eyebrow, title, description, action, children }) {
  return <section className="page min-w-0"><div className="page-heading flex-wrap"><div className="min-w-0"><div className="eyebrow">{eyebrow}</div><h1>{title}</h1>{description && <p className="page-description">{description}</p>}</div>{action}</div>{children}</section>
}
