import { useState } from 'react';
import { uploadFile } from '../api.js';

function UploadCard({ title, description, accept, files, setFiles, multiple = false }) {
  return (
    <section className="upload-card">
      <div className="upload-icon" aria-hidden="true">↑</div>
      <h3>{title}</h3>
      <p>{description}</p>
      <label className="file-button">
        Choose file{multiple ? 's' : ''}
        <input type="file" accept={accept} multiple={multiple}
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
      </label>
      {files.length > 0 && (
        <ul className="file-list">{files.map((f) => <li key={`${f.name}-${f.size}`}>{f.name}</li>)}</ul>
      )}
    </section>
  );
}

export default function NewInspection() {
  const [drawing, setDrawing] = useState([]);
  const [photos, setPhotos] = useState([]);
  const [results, setResults] = useState([]);
  const [busy, setBusy] = useState(false);

  async function handleUpload() {
    setBusy(true);
    const out = [];
    for (const file of [...drawing, ...photos]) {
      try {
        const meta = await uploadFile(file);
        out.push({ name: file.name, ok: true, detail: `${meta.content_type}, ${meta.size_bytes} bytes` });
      } catch (e) {
        out.push({ name: file.name, ok: false, detail: e.message });
      }
    }
    setResults(out);
    setBusy(false);
  }

  const nothing = drawing.length + photos.length === 0;

  return (
    <>
      <section className="workflow-heading">
        <div>
          <p className="eyebrow">NEW INSPECTION</p>
          <h2>Prepare your inspection</h2>
        </div>
      </section>

      <div className="upload-grid">
        <UploadCard title="Approved drawing" description="The cabinet drawing PDF with the parts list."
          accept="application/pdf,image/*" files={drawing} setFiles={setDrawing} />
        <UploadCard title="Cabinet photos" description="A full view plus optional close-ups."
          accept="image/jpeg,image/png" files={photos} setFiles={setPhotos} multiple />
      </div>

      <section className="notice">
        <span className="notice-mark">i</span>
        <div>
          <strong>Human review is part of the workflow</strong>
          <p>Blurry, obscured or uncertain observations go to review. A part not seen in one photo is not proof it is missing.</p>
        </div>
      </section>

      <button className="primary-button" type="button" disabled={nothing || busy} onClick={handleUpload}>
        {busy ? 'Uploading…' : 'Upload files'} <span aria-hidden="true">→</span>
      </button>
      <p className="prototype-note">Files are uploaded and checked. Running the inspection is added when the backend endpoint exists.</p>

      {results.length > 0 && (
        <ul className="upload-results">
          {results.map((r) => (
            <li key={r.name} className={r.ok ? 'ok' : 'error'}>{r.ok ? '✓' : '✗'} {r.name} — {r.detail}</li>
          ))}
        </ul>
      )}
    </>
  );
}
