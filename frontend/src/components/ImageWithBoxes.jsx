// Draws finding boxes on a photo. Boxes come in ORIGINAL image pixels (docs/contracts.md),
// so we convert them to percentages; they stay in place at any screen size.
export const STATUS_LABEL = {
  verified: 'Verified',
  potential_mismatch: 'Potential mismatch',
  needs_review: 'Needs review',
  inconclusive: 'Inconclusive',
  confirmed_by_reviewer: 'Confirmed',
  rejected_by_reviewer: 'Rejected',
  resolved_after_reinspection: 'Resolved',
};

export default function ImageWithBoxes({ image, findings, selectedId, onSelect }) {
  const boxes = findings.flatMap((f) =>
    f.evidence.filter((e) => e.image_id === image.image_id).map((e, i) => ({ f, bbox: e.bbox, key: `${f.finding_id}-${i}` })),
  );
  const pct = (v, total) => `${(v / total) * 100}%`;

  return (
    <div className="image-frame" style={{ aspectRatio: `${image.width} / ${image.height}` }}>
      {image.url ? <img src={image.url} alt={`Inspection photo ${image.image_id}`} /> : <div className="image-placeholder">No image file (synthetic)</div>}
      {boxes.map(({ f, bbox, key }) => {
        const [x1, y1, x2, y2] = bbox;
        return (
          <button
            key={key}
            type="button"
            className={`box status-${f.status} ${selectedId === f.finding_id ? 'selected' : ''}`}
            style={{ left: pct(x1, image.width), top: pct(y1, image.height), width: pct(x2 - x1, image.width), height: pct(y2 - y1, image.height) }}
            onClick={() => onSelect?.(f.finding_id)}
            title={`${f.tag ?? f.finding_id}: ${STATUS_LABEL[f.status]}`}
          >
            <span>{f.tag ?? f.finding_id}</span>
          </button>
        );
      })}
    </div>
  );
}
