import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { getInspection, reviewFinding } from '../api.js';
import ImageWithBoxes, { STATUS_LABEL } from '../components/ImageWithBoxes.jsx';
import SyntheticBanner from '../components/SyntheticBanner.jsx';
import synthetic from '../mocks/inspection.synthetic.json';

const OVERALL = { pass: 'Pass', review_required: 'Review required', mismatch_detected: 'Mismatch detected' };

export default function Results() {
  const { inspectionId } = useParams();
  const isSynthetic = inspectionId === 'synthetic';
  const [data, setData] = useState(isSynthetic ? synthetic : null);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('all');
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    if (isSynthetic) return;
    getInspection(inspectionId).then(setData).catch((e) => setError(e.message));
  }, [inspectionId, isSynthetic]);

  const shown = useMemo(
    () => (data?.findings ?? []).filter((f) => filter === 'all' || f.status === filter),
    [data, filter],
  );

  if (error) return <p className="error panel">Could not load inspection: {error}</p>;
  if (!data) return <p className="muted panel">Loading…</p>;

  const current = data.findings.find((f) => f.finding_id === selected);

  return (
    <>
      {isSynthetic && <SyntheticBanner />}
      <section className="workflow-heading">
        <div>
          <p className="eyebrow">INSPECTION {data.inspection_id}</p>
          <h2>{OVERALL[data.overall_status] ?? data.overall_status}</h2>
        </div>
        <label className="filter">
          Show{' '}
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="all">All</option>
            {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
      </section>

      <div className="results-grid">
        <div>
          {data.images.map((img) => (
            <figure key={img.image_id}>
              <ImageWithBoxes image={img} findings={shown} selectedId={selected} onSelect={setSelected} />
              {img.quality_flags.length > 0 && <figcaption className="muted">Photo flags: {img.quality_flags.join(', ')}</figcaption>}
            </figure>
          ))}
        </div>

        <table className="findings">
          <thead><tr><th>Tag</th><th>Status</th><th>Expected</th><th>Read</th><th>OCR</th></tr></thead>
          <tbody>
            {shown.map((f) => (
              <tr key={f.finding_id} className={selected === f.finding_id ? 'selected' : ''} onClick={() => setSelected(f.finding_id)}>
                <td>{f.tag ?? '—'}</td>
                <td><span className={`badge status-${f.status}`}>{STATUS_LABEL[f.status]}</span></td>
                <td>{f.expected_value ?? '—'}</td>
                <td>{f.observed_text ?? '—'}</td>
                <td>{f.ocr_confidence == null ? '—' : f.ocr_confidence.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {current && <ReviewPanel finding={current} disabled={isSynthetic} />}
    </>
  );
}

function ReviewPanel({ finding, disabled }) {
  const [reviewer, setReviewer] = useState('');
  const [note, setNote] = useState('');
  const [message, setMessage] = useState('');

  async function submit(decision) {
    try {
      await reviewFinding(finding.finding_id, { decision, reviewer, note });
      setMessage('Decision saved.');
    } catch (e) {
      setMessage(e.message);
    }
  }

  return (
    <section className="panel">
      <h3>Review {finding.tag ?? finding.finding_id}</h3>
      {finding.reason && <p className="muted">{finding.reason}</p>}
      <div className="review-form">
        <input placeholder="Your name" value={reviewer} onChange={(e) => setReviewer(e.target.value)} />
        <input placeholder="Note" value={note} onChange={(e) => setNote(e.target.value)} />
        <button type="button" disabled={disabled || !reviewer} onClick={() => submit('confirmed_by_reviewer')}>Confirm</button>
        <button type="button" disabled={disabled || !reviewer} onClick={() => submit('rejected_by_reviewer')}>Reject</button>
      </div>
      {disabled && <p className="muted">Reviews are disabled on synthetic data.</p>}
      {message && <p>{message}</p>}
    </section>
  );
}
