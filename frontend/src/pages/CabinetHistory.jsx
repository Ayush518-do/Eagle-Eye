import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getPassport } from '../api.js';

// Digital quality passport: every inspection and reinspection for one cabinet, oldest first.
export default function CabinetHistory() {
  const { cabinetId } = useParams();
  const [passport, setPassport] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    getPassport(cabinetId).then(setPassport).catch((e) => setError(e.message));
  }, [cabinetId]);

  return (
    <section className="panel">
      <p className="eyebrow">CABINET {cabinetId}</p>
      <h2>Inspection history</h2>
      {error && <p className="error">{error}</p>}
      {passport?.inspections?.length === 0 && <p className="muted">No inspections yet.</p>}
      <ol>
        {passport?.inspections?.map((i) => (
          <li key={i.inspection_id}>
            <Link to={`/inspections/${i.inspection_id}`}>{i.inspection_id}</Link> — {i.overall_status} — {i.created_at}
          </li>
        ))}
      </ol>
    </section>
  );
}
