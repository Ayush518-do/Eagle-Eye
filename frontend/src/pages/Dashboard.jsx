import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getHealth, getModelStatus, listCabinets } from '../api.js';

export default function Dashboard() {
  const [health, setHealth] = useState(null);
  const [models, setModels] = useState([]);
  const [cabinets, setCabinets] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    getHealth().then(setHealth).catch((e) => setError(e.message));
    getModelStatus().then(setModels).catch(() => {});
    listCabinets().then(setCabinets).catch(() => setCabinets(null));
  }, []);

  return (
    <>
      <section className="hero">
        <p className="eyebrow">INDUSTRIAL QUALITY ASSURANCE</p>
        <h1>See the difference.<br /><span>Inspect with evidence.</span></h1>
        <p className="hero-copy">
          Compare an approved electrical cabinet drawing with installation photographs,
          review potential discrepancies, and keep the inspection history.
        </p>
      </section>

      <section className="panel">
        <h2>System status</h2>
        {error && <p className="error">{error}</p>}
        {health && <p className="ok">Backend {health.version} is running.</p>}
        <ul className="status-list">
          {models.map((m) => (
            <li key={m.component}>
              <span className={m.available ? 'dot dot-ok' : 'dot dot-off'} />
              <strong>{m.component}</strong> — {m.detail}
            </li>
          ))}
        </ul>
      </section>

      <section className="panel">
        <h2>Cabinets</h2>
        {cabinets === null && <p className="muted">Cabinet list not available yet (backend endpoint planned).</p>}
        {Array.isArray(cabinets) && cabinets.length === 0 && <p className="muted">No cabinets yet.</p>}
        {Array.isArray(cabinets) && (
          <ul>{cabinets.map((c) => <li key={c.cabinet_id}><Link to={`/cabinets/${c.cabinet_id}`}>{c.cabinet_id}</Link></li>)}</ul>
        )}
        <p className="muted">
          UI preview with synthetic data: <Link to="/inspections/synthetic">open sample results</Link>
        </p>
      </section>
    </>
  );
}
