import React, { useRef, useState, useEffect } from 'react';
import './Timeline.css';

// A timeline of what is really on the clip. Click or drag to move the playhead.
// Caption blocks can be fixed here: double-click one, correct its words, press Enter.
export default function Timeline({ duration = 45, currentTime = 0, onSeek, tracks = [], isPlaying, onTogglePlay,
  onEditCaption, onExtend, onResizeHook }) {
  const laneRef = useRef(null);
  const [zoom, setZoom] = useState(1);
  const [dragging, setDragging] = useState(false);
  const [editing, setEditing] = useState(null);   // { id, value, error, busy } of the block being fixed
  const [extendBy, setExtendBy] = useState(0);    // seconds the video end is being dragged out by
  const [hookLen, setHookLen] = useState(null);   // the hook's length while its end is being dragged
  const [notice, setNotice] = useState('');

  const pxPerSec = 28 * zoom;

  // Follow the mouse while an edge is dragged. onMove gets the distance moved so far (seconds);
  // onUp gets the final distance once the mouse is let go.
  function trackDrag(e, onMove, onUp) {
    e.preventDefault();
    e.stopPropagation();
    const startX = e.clientX;
    const move = (ev) => onMove((ev.clientX - startX) / pxPerSec);
    const up = (ev) => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
      onUp((ev.clientX - startX) / pxPerSec);
    };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
  }

  // Drag the end of the video to make the clip longer. Released after 0.5 s: asks the server once.
  function startExtend(e) {
    setNotice('');
    trackDrag(e,
      (dx) => setExtendBy(Math.max(0, Math.min(15, dx))),
      async (dx) => {
        const by = Math.round(Math.max(0, Math.min(15, dx)) * 10) / 10;
        setExtendBy(0);
        if (by < 0.5 || !onExtend) return;
        setNotice(`Making the clip ${by} s longer…`);
        try {
          await onExtend(by);
          setNotice('');
        } catch (err) {
          setNotice(err.message);
        }
      });
  }

  // Drag the end of the hook to change how long it stays. Released: the server draws the hook again.
  function startHookResize(e, block) {
    setNotice('');
    const base = block.duration;
    trackDrag(e,
      (dx) => setHookLen(Math.max(1, Math.min(duration, base + dx))),
      async (dx) => {
        const len = Math.round(Math.max(1, Math.min(duration, base + dx)) * 10) / 10;
        setHookLen(null);
        if (Math.abs(len - base) < 0.3 || !onResizeHook) return;
        setNotice(`Hook stays for ${len} s…`);
        try {
          // a hook as long as the whole clip is saved as 0 ("whole clip"), like the editor's choice
          await onResizeHook(len >= duration - 0.05 ? 0 : len);
          setNotice('');
        } catch (err) {
          setNotice(err.message);
        }
      });
  }
  const saving = useRef(false);    // a save is already on its way (Enter, then the box closing, must not save twice)
  const cancelled = useRef(false); // Escape was pressed: the box closing must not save

  async function saveEdit(block, value) {
    if (saving.current || cancelled.current) return;
    const clean = value.trim();
    if (clean === block.title) { setEditing(null); return; }
    saving.current = true;
    setEditing((cur) => (cur ? { ...cur, busy: true, error: '' } : cur));
    try {
      await onEditCaption(block, clean);
      setEditing(null);
    } catch (e) {
      setEditing((cur) => (cur ? { ...cur, busy: false, error: e.message } : cur));
    } finally {
      saving.current = false;
    }
  }

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
          {notice && <span className="cg-text-xs cg-timeline-notice" role="status">{notice}</span>}
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
                {onExtend && t.key === 'video' && t.blocks.length > 0 && (() => {
                  const last = t.blocks[t.blocks.length - 1];
                  const end = (last.start + last.duration) * pxPerSec;
                  return (
                    <>
                      <div className="cg-timeline-extend-handle" title="Drag to make the clip longer"
                        style={{ left: end - 4 }} onMouseDown={startExtend} />
                      {extendBy > 0 && (
                        <div className="cg-timeline-extend-ghost"
                          style={{ left: end, width: extendBy * pxPerSec }}>
                          +{extendBy.toFixed(1)} s
                        </div>
                      )}
                    </>
                  );
                })()}
                {t.blocks.map((b) => {
                  const editable = b.editable && onEditCaption;
                  const isEditing = editing?.id === b.id;
                  const len = b.id === 'hook' && hookLen !== null ? hookLen : b.duration;
                  const resizable = b.resizable && onResizeHook;
                  return (
                    <React.Fragment key={b.id}>
                    <div
                      className={`cg-timeline-block cg-timeline-block--${t.key}${editable ? ' cg-timeline-block--editable' : ''}`}
                      style={{ left: b.start * pxPerSec, width: len * pxPerSec }}
                      title={editable ? `${b.title}\nDouble-click to fix the words` : b.title}
                      onDoubleClick={editable ? (e) => {
                        e.stopPropagation();
                        cancelled.current = false;
                        setEditing({ id: b.id, value: b.title, error: '', busy: false });
                      } : undefined}
                      onMouseDown={isEditing ? (e) => e.stopPropagation() : undefined}>
                      <span className="cg-block-label">{b.title}</span>
                    </div>
                    {resizable && (
                      <div className="cg-timeline-extend-handle cg-timeline-resize-handle"
                        title="Drag to change how long the hook stays"
                        style={{ left: (b.start + len) * pxPerSec - 4 }}
                        onMouseDown={(e) => startHookResize(e, b)} />
                    )}
                    {isEditing && (
                      <form className="cg-block-edit" style={{ left: b.start * pxPerSec }}
                        onMouseDown={(e) => e.stopPropagation()}
                        onSubmit={(e) => { e.preventDefault(); saveEdit(b, editing.value); }}>
                        <input
                          className="cg-block-edit-input"
                          autoFocus
                          value={editing.value}
                          disabled={editing.busy}
                          aria-label="Caption words"
                          onChange={(e) => setEditing({ ...editing, value: e.target.value })}
                          onKeyDown={(e) => {
                            if (e.key === 'Escape') { cancelled.current = true; setEditing(null); }
                          }}
                          onBlur={() => saveEdit(b, editing.value)}
                        />
                        {editing.error
                          ? <span className="cg-block-edit-error" role="alert">{editing.error}</span>
                          : <span className="cg-block-edit-hint">Enter to save · Esc to cancel</span>}
                      </form>
                    )}
                    </React.Fragment>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
