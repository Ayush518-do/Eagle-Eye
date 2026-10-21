import { useState } from 'react';

function UploadCard({ title, description, files, setFiles, multiple = false }) {
  return (
    <section className="upload-card">
      <div className="upload-icon" aria-hidden="true">↑</div>
      <h3>{title}</h3>
      <p>{description}</p>
      <label className="file-button">
        Choose image{multiple ? 's' : ''}
        <input
          type="file"
          accept="image/*"
          multiple={multiple}
          onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
        />
      </label>
      {files.length > 0 && (
        <ul className="file-list">
          {files.map((file) => <li key={`${file.name}-${file.size}`}>{file.name}</li>)}
        </ul>
      )}
    </section>
  );
}

export default function App() {
  const [referenceFiles, setReferenceFiles] = useState([]);
  const [actualFiles, setActualFiles] = useState([]);

  return (
    <main className="shell">
      <header className="topbar">
        <a className="brand" href="#home" aria-label="Eagle Eye home">
          <span className="brand-mark">E</span>
          <span>EAGLE EYE</span>
        </a>
        <span className="status-pill"><span className="status-dot" /> Prototype setup</span>
      </header>

      <section className="hero" id="home">
        <p className="eyebrow">INDUSTRIAL QUALITY ASSURANCE</p>
        <h1>See the difference.<br /><span>Inspect with evidence.</span></h1>
        <p className="hero-copy">
          Compare an approved electrical cabinet reference with installation photographs,
          review potential discrepancies, and preserve inspection history.
        </p>
      </section>

      <section className="workflow-heading">
        <div>
          <p className="eyebrow">NEW INSPECTION</p>
          <h2>Prepare your inspection</h2>
        </div>
        <span className="step-label">STEP 01 / 03</span>
      </section>

      <div className="upload-grid">
        <UploadCard
          title="Approved reference"
          description="Upload a reference layout or drawing image."
          files={referenceFiles}
          setFiles={setReferenceFiles}
        />
        <UploadCard
          title="Actual cabinet views"
          description="Upload a full view and optional close-up photographs."
          files={actualFiles}
          setFiles={setActualFiles}
          multiple
        />
      </div>

      <section className="notice">
        <span className="notice-mark">i</span>
        <div>
          <strong>Human review is part of the workflow</strong>
          <p>Blurry, obscured, or uncertain observations should be reviewed. An absent detection in one photo does not prove a component is missing.</p>
        </div>
      </section>

      <button className="primary-button" type="button" disabled>
        Inspection engine not connected yet <span aria-hidden="true">→</span>
      </button>
      <p className="prototype-note">UI scaffold only — uploads are selected in the browser and are not sent to a backend yet.</p>

      <footer>
        <span> EAGLE EYE · HACKATHON PROTOTYPE</span>
        <span>AI-assisted · Evidence-led · Human-reviewed</span>
      </footer>
    </main>
  );
}
