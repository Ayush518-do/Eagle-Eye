import React, { useState, useRef, useEffect, useCallback } from 'react';
import { ZoomIn, ZoomOut, RotateCcw, Crosshair } from 'lucide-react';

export const STATUS_COLORS = {
  defect: '#cf222e',        // Red: confirmed mismatch or confirmed missing component
  review: '#b26a00',        // Amber: uncertain, low-confidence, or review-required finding
  verified: '#1a7f37',      // Green: verified component
  ghost: '#0066b3',         // Blue: reference-position or ghost-overlay geometry
  change_region: '#8250df', // Purple: visual compare change region
  default: '#b26a00',
};

const CLASS_COLORS = {
  mcb: '#cf222e',
  breaker: '#cf222e',
  power_supply: '#1f5eff',
  psu: '#1f5eff',
  io_module: '#1a7f37',
  io: '#1a7f37',
  change_region: '#8250df',
  default: '#b26a00',
};

export default function ImageWithBoxes({
  imageUrl = '',
  boxes = [],
  ghostBoxes = [],
  missingExpectedBoxes = [],
  alignmentSet = false,
  onOpenAlignment = null,
  onResetAlignment = null,
  highlightedId = null,
  onBoxClick = null,
  imageDimensions = { width: 1600, height: 1000 },
}) {
  const containerRef = useRef(null);
  const imageRef = useRef(null);
  const [renderedSize, setRenderedSize] = useState({ width: 0, height: 0 });
  const [naturalSize, setNaturalSize] = useState(imageDimensions);

  // Pan & Zoom state
  const [scale, setScale] = useState(1);
  const [translate, setTranslate] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef({ x: 0, y: 0 });

  // Layer toggles (§2.3 & §3.4)
  const [showTags, setShowTags] = useState(true);
  const [showComponents, setShowComponents] = useState(true);
  const [findingsOnly, setFindingsOnly] = useState(false);
  const [showVerified, setShowVerified] = useState(true);
  const [showGhost, setShowGhost] = useState(true);

  // Tooltip state
  const [hoveredBox, setHoveredBox] = useState(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

  // ResizeObserver to track container & image rendered dimensions
  useEffect(() => {
    if (!containerRef.current) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        if (width > 0 && height > 0) {
          setRenderedSize({ width, height });
        }
      }
    });

    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  // Update natural dimensions when image loads
  const handleImageLoad = (e) => {
    if (e.target.naturalWidth && e.target.naturalHeight) {
      setNaturalSize({
        width: e.target.naturalWidth,
        height: e.target.naturalHeight,
      });
    }
  };

  // Zoom controls
  const handleZoomIn = () => setScale((s) => Math.min(s * 1.25, 5));
  const handleZoomOut = () => setScale((s) => Math.max(s / 1.25, 0.4));
  const handleResetZoom = () => {
    setScale(1);
    setTranslate({ x: 0, y: 0 });
  };

  // Mouse wheel zoom
  const handleWheel = useCallback((e) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
    setScale((prevScale) => {
      const nextScale = Math.min(Math.max(prevScale * zoomFactor, 0.4), 5);
      return nextScale;
    });
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.addEventListener('wheel', handleWheel, { passive: false });
    return () => el.removeEventListener('wheel', handleWheel);
  }, [handleWheel]);

  // Pan interaction
  const handleMouseDown = (e) => {
    if (e.button !== 0) return; // Primary click only
    setIsDragging(true);
    dragStartRef.current = {
      x: e.clientX - translate.x,
      y: e.clientY - translate.y,
    };
  };

  const handleMouseMove = (e) => {
    if (isDragging) {
      setTranslate({
        x: e.clientX - dragStartRef.current.x,
        y: e.clientY - dragStartRef.current.y,
      });
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  // Box hover for tooltip
  const handleBoxMouseEnter = (box, e) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (rect) {
      setTooltipPos({
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
      });
    }
    setHoveredBox(box);
  };

  const handleBoxMouseMove = (e) => {
    if (!hoveredBox) return;
    const rect = containerRef.current?.getBoundingClientRect();
    if (rect) {
      setTooltipPos({
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
      });
    }
  };

  const handleBoxMouseLeave = () => {
    setHoveredBox(null);
  };

  // Calculate box color based on defect status convention
  const getBoxColor = (box) => {
    if (box.color) return box.color;
    if (box.isGhost || box.isExpectedPosition) return STATUS_COLORS.ghost;
    if (box.className === 'change_region') return STATUS_COLORS.change_region;

    const status = (box.status || '').toLowerCase();
    const type = (box.issue_type || '').toLowerCase();

    // Red: confirmed mismatch, rating mismatch, misplaced, or confirmed missing
    if (
      status === 'mismatch' ||
      status === 'potential_mismatch' ||
      status === 'rejected_by_reviewer' ||
      type === 'rating_mismatch' ||
      type === 'misplaced' ||
      (type === 'missing' && status === 'confirmed_by_reviewer')
    ) {
      return STATUS_COLORS.defect;
    }

    // Green: verified component
    if (status === 'verified' || status === 'pass' || (status === 'confirmed_by_reviewer' && type === 'verified')) {
      return STATUS_COLORS.verified;
    }

    // Amber: uncertain, low-confidence, or review-required finding
    return STATUS_COLORS.review;
  };

  // Stroke style maps to the FIRST source on the box: detector = solid (fine-tuned),
  // zero_shot = long dash, ocr = short dash, missing / expected geometry = dashed envelope.
  const getStrokeDash = (box) => {
    if (box.isGhost || box.isExpectedPosition || box.issue_type === 'missing') return '6,4';
    const src = (box.sources || [])[0];
    if (src === 'zero_shot') return '10,5';
    if (src === 'ocr') return '3,3';
    return ''; // detector, manual, or verified → solid
  };

  const viewBoxWidth = naturalSize.width || 1600;
  const viewBoxHeight = naturalSize.height || 1000;

  return (
    <div className="image-viewer-card">
      {/* Viewer Toolbar */}
      <div className="image-viewer-toolbar">
        <div className="viewer-controls">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={handleZoomIn}
            title="Zoom In"
            aria-label="Zoom in"
          >
            <ZoomIn size={14} />
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={handleZoomOut}
            title="Zoom Out"
            aria-label="Zoom out"
          >
            <ZoomOut size={14} />
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={handleResetZoom}
            title="Reset View"
            aria-label="Reset view"
          >
            <RotateCcw size={14} />
            <span>Reset ({(scale * 100).toFixed(0)}%)</span>
          </button>
        </div>

        {/* Layer Toggles (§2.3 & §3.4) */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '11px', fontWeight: 600, flexWrap: 'wrap' }}>
          <span style={{ color: 'var(--color-text-muted)' }}>Layers:</span>
          <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={showTags}
              onChange={(e) => setShowTags(e.target.checked)}
            />
            <span>Tags</span>
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={showComponents}
              onChange={(e) => setShowComponents(e.target.checked)}
            />
            <span>Components</span>
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={showVerified}
              onChange={(e) => setShowVerified(e.target.checked)}
            />
            <span>Verified</span>
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={findingsOnly}
              onChange={(e) => setFindingsOnly(e.target.checked)}
            />
            <span>Defects only</span>
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer', color: showGhost ? 'var(--color-primary)' : 'inherit' }}>
            <input
              type="checkbox"
              checked={showGhost}
              onChange={(e) => setShowGhost(e.target.checked)}
            />
            <span>Ghost overlay</span>
          </label>
        </div>

        {/* Alignment Actions (§3.4) */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          {onOpenAlignment && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={onOpenAlignment}
              title="Align 4 corners between drawing and photo"
              style={{ fontSize: '11px', padding: '3px 8px' }}
            >
              <Crosshair size={12} />
              <span>{alignmentSet ? 'Edit Alignment' : 'Align 4 Corners'}</span>
            </button>
          )}
          {alignmentSet && onResetAlignment && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={onResetAlignment}
              title="Reset saved alignment"
              style={{ fontSize: '11px', padding: '3px 8px' }}
            >
              <RotateCcw size={12} />
              <span>Reset</span>
            </button>
          )}
        </div>

        {/* Legend — defect status convention + source strokes */}
        <div className="viewer-legend">
          <span className="legend-item" title="Confirmed mismatch, wrong rating, or missing component">
            <span className="legend-swatch" style={{ backgroundColor: STATUS_COLORS.defect }} />
            <span>Mismatch / Missing</span>
          </span>
          <span className="legend-item" title="Low confidence, uncertain reading, or needs review">
            <span className="legend-swatch" style={{ backgroundColor: STATUS_COLORS.review }} />
            <span>Needs Review</span>
          </span>
          <span className="legend-item" title="Component verified matching drawing">
            <span className="legend-swatch" style={{ backgroundColor: STATUS_COLORS.verified }} />
            <span>Verified</span>
          </span>
          <span className="legend-item" title="Expected reference installation position or ghost outline">
            <span className="legend-swatch" style={{ backgroundColor: 'transparent', border: `2px dashed ${STATUS_COLORS.ghost}` }} />
            <span>Reference / Expected</span>
          </span>
          <span className="legend-sep" aria-hidden="true" />
          <span className="legend-item" title="Trained RF-DETR detector (solid border)">
            <span className="legend-stroke solid" />
            <span>Detector</span>
          </span>
          <span className="legend-item" title="OWLv2 zero-shot detector (long dashed border)">
            <span className="legend-stroke long-dash" />
            <span>Zero-shot</span>
          </span>
          <span className="legend-item" title="OCR tag reader (short dashed border)">
            <span className="legend-stroke short-dash" />
            <span>OCR</span>
          </span>
          {showGhost && (
            <>
              <span className="legend-sep" aria-hidden="true" />
              <span className="legend-item" title="SIFT visual difference regions">
                <span className="legend-swatch" style={{ backgroundColor: STATUS_COLORS.change_region }} />
                <span>Change Region</span>
              </span>
            </>
          )}
        </div>
      </div>

      {/* Canvas Viewport */}
      <div
        ref={containerRef}
        className={`image-canvas-container ${isDragging ? 'panning' : ''}`}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={() => {
          setIsDragging(false);
          setHoveredBox(null);
        }}
      >
        <div
          className="canvas-transform-layer"
          style={{
            transform: `translate(${translate.x}px, ${translate.y}px) scale(${scale})`,
            width: `${viewBoxWidth}px`,
            height: `${viewBoxHeight}px`,
          }}
        >
          {/* Base Cabinet Image or Industrial Schematic Canvas */}
          {imageUrl ? (
            <img
              ref={imageRef}
              src={imageUrl}
              alt="Electrical Cabinet Scan"
              className="canvas-image"
              onLoad={handleImageLoad}
              style={{ width: `${viewBoxWidth}px`, height: `${viewBoxHeight}px` }}
            />
          ) : (
            <svg
              className="canvas-image"
              width={viewBoxWidth}
              height={viewBoxHeight}
              viewBox={`0 0 ${viewBoxWidth} ${viewBoxHeight}`}
              style={{ backgroundColor: '#131b26' }}
            >
              {/* Industrial Cabinet Mock Backdrop */}
              <rect x="0" y="0" width={viewBoxWidth} height={viewBoxHeight} fill="#131b26" />
              {/* Cabinet Enclosure Outline */}
              <rect
                x="80"
                y="80"
                width={viewBoxWidth - 160}
                height={viewBoxHeight - 160}
                fill="#1c2534"
                stroke="#2f3e55"
                strokeWidth="4"
              />
              {/* DIN Rails */}
              <line x1="120" y1="210" x2={viewBoxWidth - 120} y2="210" stroke="#485973" strokeWidth="12" strokeDasharray="16, 6" />
              <line x1="120" y1="690" x2={viewBoxWidth - 120} y2="690" stroke="#485973" strokeWidth="12" strokeDasharray="16, 6" />
              <text x="140" y="140" fill="#6c809e" fontSize="18" fontWeight="600" fontFamily="sans-serif">
                ENCLOSURE ELEVATION — 24V DC / 230V AC PANEL
              </text>
              <text x="140" y="165" fill="#4d5f77" fontSize="13" fontFamily="monospace">
                RESOLUTION: {viewBoxWidth} x {viewBoxHeight} PX
              </text>
            </svg>
          )}

          {/* SVG Bounding Boxes Overlay */}
          <svg
            className="canvas-svg-overlay"
            viewBox={`0 0 ${viewBoxWidth} ${viewBoxHeight}`}
            width={viewBoxWidth}
            height={viewBoxHeight}
          >
            {boxes
              .filter((box) => {
                const isVerified = box.status === 'verified' || box.status === 'pass' || box.issue_type === 'verified';
                if (!showVerified && isVerified) return false;
                if (findingsOnly && isVerified) return false;
                return true;
              })
              .map((box) => {
                const [x1, y1, x2, y2] = box.bbox;
                const w = Math.max(x2 - x1, 10);
                const h = Math.max(y2 - y1, 10);
                const isSelected = highlightedId === box.id;
                const isDimmed = highlightedId !== null && !isSelected;
                const strokeColor = getBoxColor(box);

                return (
                  <g
                    key={box.id}
                    className={`svg-box-group ${isSelected ? 'selected' : ''} ${isDimmed ? 'dimmed' : ''}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      if (onBoxClick) onBoxClick(box.id);
                    }}
                    onMouseEnter={(e) => handleBoxMouseEnter(box, e)}
                    onMouseMove={handleBoxMouseMove}
                    onMouseLeave={handleBoxMouseLeave}
                  >
                    {/* Bounding Box Rectangle (Component Layer) */}
                    {showComponents && (
                      <rect
                        x={x1}
                        y={y1}
                        width={w}
                        height={h}
                        className="svg-box-rect"
                        stroke={strokeColor}
                        strokeDasharray={getStrokeDash(box)}
                        rx="3"
                        ry="3"
                      />
                    )}

                    {/* Tag Label Badge Header (Tag Layer) */}
                    {showTags && (
                      <>
                        <rect
                          x={x1}
                          y={Math.max(y1 - 22, 2)}
                          width={Math.min(Math.max((box.label || '').length * 9 + 16, 50), w + 20)}
                          height="20"
                          fill={strokeColor}
                          rx="2"
                          ry="2"
                          className="svg-box-label-bg"
                        />
                        <text
                          x={x1 + 6}
                          y={Math.max(y1 - 8, 16)}
                          className="svg-box-label"
                        >
                          {box.label || box.id}
                        </text>
                      </>
                    )}
                  </g>
                );
              })}

            {/* Ghost Overlay Layer (§3.4, contract E) */}
            {showGhost &&
              ghostBoxes.map((ghost, idx) => {
                const [x1, y1, x2, y2] = ghost.bbox || [0, 0, 0, 0];
                const w = Math.max(x2 - x1, 10);
                const h = Math.max(y2 - y1, 10);
                const ghostColor = STATUS_COLORS.ghost;

                return (
                  <g key={`ghost-${idx}`} className="ghost-box-group">
                    <rect
                      x={x1}
                      y={y1}
                      width={w}
                      height={h}
                      fill="rgba(0, 102, 179, 0.05)"
                      stroke={ghostColor}
                      strokeWidth="2"
                      strokeDasharray="6,4"
                      rx="3"
                      ry="3"
                    />
                    <rect
                      x={x1}
                      y={Math.max(y1 - 18, 2)}
                      width={Math.min((ghost.tag || '').length * 8 + 32, w + 40)}
                      height="16"
                      fill={ghostColor}
                      opacity="0.9"
                      rx="2"
                      ry="2"
                    />
                    <text
                      x={x1 + 4}
                      y={Math.max(y1 - 6, 14)}
                      fontSize="10"
                      fontWeight="600"
                      fill="#ffffff"
                      fontFamily="monospace"
                    >
                      Ghost: {ghost.tag}
                    </text>
                  </g>
                );
              })}

            {/* Missing Component Expected Spot (§3.4, contract E) */}
            {showComponents &&
              missingExpectedBoxes.map((item, idx) => {
                const [x1, y1, x2, y2] = item.expected_bbox || [0, 0, 0, 0];
                const w = Math.max(x2 - x1, 10);
                const h = Math.max(y2 - y1, 10);
                const isSelected = item.id && item.id === highlightedId;
                const isDimmed = highlightedId !== null && !isSelected;
                const tagLabel = item.tag || item.expected_tag || '';

                return (
                  <g
                    key={`missing-exp-${idx}`}
                    className={`missing-expected-group ${isSelected ? 'selected' : ''} ${isDimmed ? 'dimmed' : ''}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      if (item.id && onBoxClick) onBoxClick(item.id);
                    }}
                    style={{ cursor: item.id ? 'pointer' : 'default' }}
                  >
                    <rect
                      x={x1}
                      y={y1}
                      width={w}
                      height={h}
                      fill={isSelected ? 'rgba(207, 34, 46, 0.25)' : 'rgba(207, 34, 46, 0.08)'}
                      stroke={STATUS_COLORS.defect}
                      strokeWidth={isSelected ? '3.5' : '2.5'}
                      strokeDasharray="6,4"
                      rx="3"
                      ry="3"
                    />
                    {showTags && (
                      <>
                        <rect
                          x={x1}
                          y={Math.max(y1 - 20, 2)}
                          width={Math.min(tagLabel.length * 8 + 70, w + 60)}
                          height="18"
                          fill={STATUS_COLORS.defect}
                          rx="2"
                          ry="2"
                        />
                        <text
                          x={x1 + 4}
                          y={Math.max(y1 - 7, 15)}
                          fontSize="10"
                          fontWeight="700"
                          fill="#ffffff"
                        >
                          MISSING: {tagLabel}
                        </text>
                      </>
                    )}
                  </g>
                );
              })}
          </svg>
        </div>

        {/* Floating Approximate Ghost Notice (§3.4) */}
        {showGhost && (ghostBoxes.length > 0 || missingExpectedBoxes.length > 0) && (
          <div
            style={{
              position: 'absolute',
              top: '12px',
              right: '12px',
              backgroundColor: 'rgba(255, 255, 255, 0.94)',
              border: '1px solid var(--color-border)',
              borderRadius: '4px',
              padding: '4px 10px',
              fontSize: '11px',
              fontWeight: 600,
              color: 'var(--color-text-muted)',
              boxShadow: '0 2px 6px rgba(0,0,0,0.06)',
              zIndex: 10,
              pointerEvents: 'none',
            }}
          >
            Approximate positions from the drawing
          </div>
        )}

        {/* Hover Tooltip (§2.3) */}
        {hoveredBox && (
          <div
            className="viewer-tooltip"
            style={{
              left: `${tooltipPos.x}px`,
              top: `${tooltipPos.y}px`,
            }}
          >
            <div className="viewer-tooltip-title">
              {hoveredBox.label || hoveredBox.id}
            </div>
            <div className="viewer-tooltip-meta">
              Class: <strong>{hoveredBox.className || hoveredBox.class_name || 'Component'}</strong>
            </div>
            {hoveredBox.status && (
              <div className="viewer-tooltip-meta">
                Status: <strong style={{ textTransform: 'capitalize' }}>{hoveredBox.status.replace(/_/g, ' ')}</strong>
              </div>
            )}
            {hoveredBox.sources && hoveredBox.sources.length > 0 && (
              <div className="viewer-tooltip-meta">
                Sources: <strong>{hoveredBox.sources.join(', ')}</strong>
              </div>
            )}
            {hoveredBox.confidence != null && (
              <div className="viewer-tooltip-meta">
                Detector Conf: <strong>{(hoveredBox.confidence * 100).toFixed(1)}%</strong>
              </div>
            )}
            {hoveredBox.ocr_confidence != null && (
              <div className="viewer-tooltip-meta">
                OCR Conf: <strong>{(hoveredBox.ocr_confidence * 100).toFixed(1)}%</strong>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
