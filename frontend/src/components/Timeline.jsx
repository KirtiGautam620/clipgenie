import React, { useRef, useState, useEffect } from 'react';
import './Timeline.css';

export default function Timeline({
  duration = 45,
  currentTime = 0,
  onSeek,
  tracksData,
  selectedItemId,
  onSelectItem,
  isPlaying,
  onTogglePlay,
  onSplit,
  onDeleteSelected
}) {
  const containerRef = useRef(null);
  const laneRef = useRef(null);
  const [zoom, setZoom] = useState(1);
  const [isSnapping, setIsSnapping] = useState(true);
  const [isDraggingPlayhead, setIsDraggingPlayhead] = useState(false);

  // Pixels per second at 1x zoom
  const pxPerSec = 28 * zoom;
  const totalWidth = Math.max(800, duration * pxPerSec);

  // Time format helper (00:12.3)
  const formatTime = (sec) => {
    const mins = Math.floor(sec / 60);
    const secs = Math.floor(sec % 60);
    const tenths = Math.floor((sec % 1) * 10);
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${tenths}`;
  };

  // Generate ruler markers every 5 seconds (or 1s at higher zoom)
  const step = zoom >= 1.8 ? 1 : zoom >= 1 ? 2 : 5;
  const markers = [];
  for (let s = 0; s <= duration; s += step) {
    markers.push(s);
  }

  // Handle timeline scrubber click/drag
  const handleTimelineInteraction = (e) => {
    if (!laneRef.current) return;
    const rect = laneRef.current.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    let targetTime = Math.max(0, Math.min(duration, clickX / pxPerSec));
    if (isSnapping) {
      // Snap to nearest 0.25s
      targetTime = Math.round(targetTime * 4) / 4;
    }
    if (onSeek) onSeek(targetTime);
  };

  const handleMouseDown = (e) => {
    setIsDraggingPlayhead(true);
    handleTimelineInteraction(e);
  };

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isDraggingPlayhead) return;
      handleTimelineInteraction(e);
    };
    const handleMouseUp = () => {
      if (isDraggingPlayhead) setIsDraggingPlayhead(false);
    };

    if (isDraggingPlayhead) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    }
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDraggingPlayhead, duration, pxPerSec, isSnapping]);

  return (
    <div className="cg-timeline-dock" ref={containerRef}>
      {/* Timeline Controls Bar */}
      <div className="cg-timeline-toolbar">
        <div className="cg-timeline-tools-left">
          <button
            type="button"
            className="cg-btn cg-btn--sm cg-btn--secondary"
            onClick={onTogglePlay}
            title={isPlaying ? "Pause (Space)" : "Play (Space)"}
          >
            {isPlaying ? "⏸ Pause" : "▶ Play"}
          </button>
          <div className="cg-timeline-time-badge">
            <span className="cg-time-current">{formatTime(currentTime)}</span>
            <span className="cg-time-sep">/</span>
            <span className="cg-time-total">{formatTime(duration)}</span>
          </div>

          <div className="cg-timeline-divider-v" />

          <button
            type="button"
            className={`cg-tool-pill ${isSnapping ? 'active' : ''}`}
            onClick={() => setIsSnapping(!isSnapping)}
            title="Toggle Magnet Snapping"
          >
            🧲 Snap {isSnapping ? 'On' : 'Off'}
          </button>

          <button
            type="button"
            className="cg-tool-pill"
            onClick={() => onSplit && onSplit(currentTime)}
            title="Split Clip at Playhead"
          >
            ✂️ Split
          </button>

          {selectedItemId && (
            <button
              type="button"
              className="cg-tool-pill cg-tool-pill--danger"
              onClick={onDeleteSelected}
              title="Delete Selected Item"
            >
              🗑️ Delete
            </button>
          )}
        </div>

        <div className="cg-timeline-tools-right">
          <span className="cg-text-xs cg-text-muted">Zoom</span>
          <input
            type="range"
            min="0.6"
            max="2.5"
            step="0.1"
            value={zoom}
            onChange={(e) => setZoom(parseFloat(e.target.value))}
            className="cg-range"
            style={{ width: 100 }}
            title="Timeline Zoom"
          />
          <span className="cg-text-xs cg-text-secondary">{Math.round(zoom * 100)}%</span>
        </div>
      </div>

      {/* Timeline Body: Track Headers (Fixed left) + Scrollable Canvas */}
      <div className="cg-timeline-scroll-container">
        {/* Track Headers Column */}
        <div className="cg-timeline-headers-col">
          <div className="cg-track-header-top">Tracks</div>
          <div className="cg-track-header">
            <span className="cg-track-dot cg-track-dot--broll" />
            <span>AI B-Roll</span>
          </div>
          <div className="cg-track-header">
            <span className="cg-track-dot cg-track-dot--video" />
            <span>Main Video</span>
          </div>
          <div className="cg-track-header">
            <span className="cg-track-dot cg-track-dot--captions" />
            <span>Captions</span>
          </div>
          <div className="cg-track-header">
            <span className="cg-track-dot cg-track-dot--music" />
            <span>Music</span>
          </div>
          <div className="cg-track-header">
            <span className="cg-track-dot cg-track-dot--sfx" />
            <span>Sound FX</span>
          </div>
          <div className="cg-track-header">
            <span className="cg-track-dot cg-track-dot--effects" />
            <span>Effects</span>
          </div>
        </div>

        {/* Scrollable Tracks Area */}
        <div
          className="cg-timeline-canvas-scroll"
          onMouseDown={handleMouseDown}
        >
          {/* Ruler */}
          <div className="cg-timeline-ruler" style={{ width: totalWidth }}>
            {markers.map((s) => (
              <div
                key={s}
                className="cg-ruler-tick"
                style={{ left: s * pxPerSec }}
              >
                <div className="cg-ruler-line" />
                <span className="cg-ruler-label">{formatTime(s)}</span>
              </div>
            ))}
          </div>

          {/* Tracks Area */}
          <div
            className="cg-timeline-lanes-area"
            ref={laneRef}
            style={{ width: totalWidth }}
          >
            {/* Playhead Needle */}
            <div
              className="cg-timeline-playhead"
              style={{ left: currentTime * pxPerSec }}
            >
              <div className="cg-playhead-cap" />
              <div className="cg-playhead-line" />
            </div>

            {/* 1. AI B-Roll Track */}
            <div className="cg-timeline-lane">
              {tracksData.broll?.map((item) => (
                <div
                  key={item.id}
                  className={`cg-timeline-block cg-timeline-block--broll ${selectedItemId === item.id ? 'selected' : ''}`}
                  style={{
                    left: item.start * pxPerSec,
                    width: item.duration * pxPerSec,
                  }}
                  onClick={(e) => { e.stopPropagation(); onSelectItem(item); }}
                >
                  <span className="cg-block-icon">✨</span>
                  <span className="cg-block-label">{item.title}</span>
                </div>
              ))}
            </div>

            {/* 2. Main Video Track */}
            <div className="cg-timeline-lane">
              {tracksData.video?.map((item) => (
                <div
                  key={item.id}
                  className={`cg-timeline-block cg-timeline-block--video ${selectedItemId === item.id ? 'selected' : ''}`}
                  style={{
                    left: item.start * pxPerSec,
                    width: item.duration * pxPerSec,
                  }}
                  onClick={(e) => { e.stopPropagation(); onSelectItem(item); }}
                >
                  <span className="cg-block-icon">🎬</span>
                  <span className="cg-block-label">{item.title}</span>
                </div>
              ))}
            </div>

            {/* 3. Captions Track */}
            <div className="cg-timeline-lane">
              {tracksData.captions?.map((item) => (
                <div
                  key={item.id}
                  className={`cg-timeline-block cg-timeline-block--captions ${selectedItemId === item.id ? 'selected' : ''}`}
                  style={{
                    left: item.start * pxPerSec,
                    width: item.duration * pxPerSec,
                  }}
                  onClick={(e) => { e.stopPropagation(); onSelectItem(item); }}
                >
                  <span className="cg-block-icon">💬</span>
                  <span className="cg-block-label">{item.title}</span>
                </div>
              ))}
            </div>

            {/* 4. Music Track */}
            <div className="cg-timeline-lane">
              {tracksData.music?.map((item) => (
                <div
                  key={item.id}
                  className={`cg-timeline-block cg-timeline-block--music ${selectedItemId === item.id ? 'selected' : ''}`}
                  style={{
                    left: item.start * pxPerSec,
                    width: item.duration * pxPerSec,
                  }}
                  onClick={(e) => { e.stopPropagation(); onSelectItem(item); }}
                >
                  <span className="cg-block-icon">🎵</span>
                  <span className="cg-block-label">{item.title} ({Math.round((item.volume ?? 0.6) * 100)}%)</span>
                </div>
              ))}
            </div>

            {/* 5. SFX Track */}
            <div className="cg-timeline-lane">
              {tracksData.sfx?.map((item) => (
                <div
                  key={item.id}
                  className={`cg-timeline-block cg-timeline-block--sfx ${selectedItemId === item.id ? 'selected' : ''}`}
                  style={{
                    left: item.start * pxPerSec,
                    width: item.duration * pxPerSec,
                  }}
                  onClick={(e) => { e.stopPropagation(); onSelectItem(item); }}
                >
                  <span className="cg-block-icon">💥</span>
                  <span className="cg-block-label">{item.title}</span>
                </div>
              ))}
            </div>

            {/* 6. Effects Track */}
            <div className="cg-timeline-lane">
              {tracksData.effects?.map((item) => (
                <div
                  key={item.id}
                  className={`cg-timeline-block cg-timeline-block--effects ${selectedItemId === item.id ? 'selected' : ''}`}
                  style={{
                    left: item.start * pxPerSec,
                    width: item.duration * pxPerSec,
                  }}
                  onClick={(e) => { e.stopPropagation(); onSelectItem(item); }}
                >
                  <span className="cg-block-icon">⚡</span>
                  <span className="cg-block-label">{item.title}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

