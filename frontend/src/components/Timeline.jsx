import React, { useRef, useState, useEffect } from 'react';
import './Timeline.css';

// A read-only timeline of what is really on the clip. Click or drag to move the playhead.
export default function Timeline({ duration = 45, currentTime = 0, onSeek, tracks = [], isPlaying, onTogglePlay }) {
  const laneRef = useRef(null);
  const [zoom, setZoom] = useState(1);
  const [dragging, setDragging] = useState(false);

  const pxPerSec = 28 * zoom;
  const totalWidth = Math.max(800, duration * pxPerSec);

  const formatTime = (sec) => {
    const mins = Math.floor(sec / 60);
    const secs = Math.floor(sec % 60);
    const tenths = Math.floor((sec % 1) * 10);
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${tenths}`;
  };

  const step = zoom >= 1.8 ? 1 : zoom >= 1 ? 2 : 5;
  const markers = [];
  for (let s = 0; s <= duration; s += step) markers.push(s);

  const seekFromEvent = (e) => {
    if (!laneRef.current) return;
    const rect = laneRef.current.getBoundingClientRect();
    if (onSeek) onSeek(Math.max(0, Math.min(duration, (e.clientX - rect.left) / pxPerSec)));
  };

  useEffect(() => {
    if (!dragging) return undefined;
    const move = (e) => seekFromEvent(e);
    const up = () => setDragging(false);
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
    return () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
    };
  }, [dragging, duration, pxPerSec]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="cg-timeline-dock">
      <div className="cg-timeline-toolbar">
        <div className="cg-timeline-tools-left">
          <button type="button" className="cg-btn cg-btn--sm cg-btn--secondary" onClick={onTogglePlay}
            title={isPlaying ? 'Pause' : 'Play'}>
            {isPlaying ? '⏸ Pause' : '▶ Play'}
          </button>
          <div className="cg-timeline-time-badge">
            <span className="cg-time-current">{formatTime(currentTime)}</span>
            <span className="cg-time-sep">/</span>
            <span className="cg-time-total">{formatTime(duration)}</span>
          </div>
        </div>
        <div className="cg-timeline-tools-right">
          <span className="cg-text-xs cg-text-muted">Zoom</span>
          <input type="range" min="0.6" max="2.5" step="0.1" value={zoom} className="cg-range"
            onChange={(e) => setZoom(parseFloat(e.target.value))} style={{ width: 100 }} title="Timeline zoom" />
          <span className="cg-text-xs cg-text-secondary">{Math.round(zoom * 100)}%</span>
        </div>
      </div>

      <div className="cg-timeline-scroll-container">
        <div className="cg-timeline-headers-col">
          <div className="cg-track-header-top">Tracks</div>
          {tracks.map((t) => (
            <div className="cg-track-header" key={t.key}>
              <span className={`cg-track-dot cg-track-dot--${t.key}`} />
              <span>{t.label}</span>
            </div>
          ))}
        </div>

        <div className="cg-timeline-canvas-scroll" onMouseDown={(e) => { setDragging(true); seekFromEvent(e); }}>
          <div className="cg-timeline-ruler" style={{ width: totalWidth }}>
            {markers.map((s) => (
              <div key={s} className="cg-ruler-tick" style={{ left: s * pxPerSec }}>
                <div className="cg-ruler-line" />
                <span className="cg-ruler-label">{formatTime(s)}</span>
              </div>
            ))}
          </div>

          <div className="cg-timeline-lanes-area" ref={laneRef} style={{ width: totalWidth }}>
            <div className="cg-timeline-playhead" style={{ left: currentTime * pxPerSec }}>
              <div className="cg-playhead-cap" />
              <div className="cg-playhead-line" />
            </div>
            {tracks.map((t) => (
              <div className="cg-timeline-lane" key={t.key}>
                {t.blocks.map((b) => (
                  <div key={b.id} className={`cg-timeline-block cg-timeline-block--${t.key}`}
                    style={{ left: b.start * pxPerSec, width: b.duration * pxPerSec }} title={b.title}>
                    <span className="cg-block-label">{b.title}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
