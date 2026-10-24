import React, { useState, useRef, useEffect, useCallback } from 'react';
import { ZoomIn, ZoomOut, RotateCcw, Crosshair } from 'lucide-react';

const CLASS_COLORS = {
  mcb: '#cf222e',          // Breaker: Industrial Red
  breaker: '#cf222e',
  power_supply: '#1f5eff', // Power Supply: Blue
  psu: '#1f5eff',
  io_module: '#1a7f37',    // I/O Module: Forest Green
  io: '#1a7f37',
  default: '#f0a500',      // Default / Other: Amber
};

export default function ImageWithBoxes({
  imageUrl = '',
  boxes = [],
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

  // Calculate box color based on class
  const getBoxColor = (box) => {
    if (box.color) return box.color;
    const cls = (box.className || box.class_name || '').toLowerCase();
    return CLASS_COLORS[cls] || CLASS_COLORS.default;
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

        {/* Component Legend */}
        <div className="viewer-legend">
          <span className="legend-item">
            <span className="legend-swatch" style={{ backgroundColor: CLASS_COLORS.mcb }} />
            <span>Breaker (MCB)</span>
          </span>
          <span className="legend-item">
            <span className="legend-swatch" style={{ backgroundColor: CLASS_COLORS.power_supply }} />
            <span>Power Supply</span>
          </span>
          <span className="legend-item">
            <span className="legend-swatch" style={{ backgroundColor: CLASS_COLORS.io_module }} />
            <span>I/O Module</span>
          </span>
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
            {boxes.map((box) => {
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
                  {/* Bounding Box Rectangle */}
                  <rect
                    x={x1}
                    y={y1}
                    width={w}
                    height={h}
                    className="svg-box-rect"
                    stroke={strokeColor}
                    rx="3"
                    ry="3"
                  />
                  {/* Tag Label Badge Header */}
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
                </g>
              );
            })}
          </svg>
        </div>

        {/* Hover Tooltip */}
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
