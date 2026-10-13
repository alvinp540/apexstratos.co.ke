export default function Page({ eyebrow, title, description, action, children }) {
  return <section className="page"><div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1>{description && <p className="page-description">{description}</p>}</div>{action}</div>{children}</section>
}
