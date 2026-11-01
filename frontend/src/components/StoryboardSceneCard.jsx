import React, { useEffect, useRef, useState } from 'react';
import { getJSON } from '../api.js';

const MOTION = { hold: 'Hold still', push_in: 'Push in', pull_out: 'Pull out', pan_left: 'Pan left',
  pan_right: 'Pan right', pan_up: 'Pan up', pan_down: 'Pan down' };
const TRANSITION = { cut: 'Hard cut', fade: 'Fade', slide_left: 'Slide left', slide_right: 'Slide right',
  wipe_left: 'Wipe' };
const SHARP = {
  sharp: ['Sharp', 'cg-badge--success'],
  ok: ['Slightly soft', 'cg-badge--muted'],
  soft: ['Soft: a small crop of this photo', 'cg-badge--warning'],
};

function useDebounced(value, ms) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export default function StoryboardSceneCard({
  storyboardId, scene, index, total, selected, geometry, aspect, options, copied,
  onSelect, onChange, onMove, onDuplicate, onRemove, onRebuildPrompt, onCopy, onGeometry,
}) {
  const query = new URLSearchParams({
    zoom: scene.zoom, motion: scene.motion, intensity: scene.intensity, fx: scene.focus[0], fy: scene.focus[1],
  }).toString();
  const settled = useDebounced(query, 250);
  const first = useRef(true);

  // Where this scene looks, and how sharp it will be, follow the edits (the server does the geometry).
  useEffect(() => {
    if (first.current) {
      first.current = false;
      if (geometry) return undefined;            // already known from the saved storyboard
    }
    let live = true;
    getJSON(`/api/storyboards/${storyboardId}/geometry?${settled}`)
      .then((g) => live && onGeometry(scene.id, g)).catch(() => {});
    return () => { live = false; };
  }, [settled]); // eslint-disable-line react-hooks/exhaustive-deps

  const frame = (which) => `/api/storyboards/${storyboardId}/frame.jpg?${settled}&which=${which}&w=320`;
  const sharp = geometry && SHARP[geometry.sharpness.label];
  const shape = aspect === '16:9' ? 'cg-sb-frame--wide' : 'cg-sb-frame--tall';

  return (
    <article className={`cg-card cg-sb-scene ${selected ? 'selected' : ''}`} onClick={onSelect}
      aria-label={`Scene ${index + 1}: ${scene.title}`}>
      <header className="cg-sb-scene-head">
        <span className="cg-sb-num">{index + 1}</span>
        <input className="cg-input cg-sb-title" value={scene.title} maxLength={60} aria-label={`Scene ${index + 1} title`}
          onChange={(e) => onChange({ title: e.target.value })} />
        <div className="cg-sb-tools">
          <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" disabled={index === 0}
            onClick={() => onMove(-1)} aria-label="Move up">↑</button>
          <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" disabled={index === total - 1}
            onClick={() => onMove(1)} aria-label="Move down">↓</button>
          <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" disabled={total >= options.limits.saved_scenes[1]}
            onClick={onDuplicate}>Duplicate</button>
          <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" disabled={total <= 1}
            onClick={onRemove}>Delete</button>
        </div>
      </header>

      <div className="cg-sb-scene-body">
        <div>
          <p className="cg-sb-caption">Preview from your photo: framing only</p>
          <div className="cg-sb-frames">
            <figure><img className={shape} src={frame('start')} alt={`Scene ${index + 1} start`} /><figcaption>Start</figcaption></figure>
            <figure><img className={shape} src={frame('end')} alt={`Scene ${index + 1} end`} /><figcaption>End</figcaption></figure>
          </div>
          {sharp && (
            <span className={`cg-badge ${sharp[1]}`} title={`${geometry.sharpness.crop_px[0]} x ${geometry.sharpness.crop_px[1]} pixels of your photo`}>
              {sharp[0]}
            </span>
          )}
        </div>

        <div className="cg-sb-fields">
          <div className="cg-sb-controls">
            <label className="cg-sb-ctl">Length (s)
              <input type="number" className="cg-input" min={options.limits.duration[0]} max={options.limits.duration[1]}
                step="0.5" value={scene.duration} onChange={(e) => onChange({ duration: Number(e.target.value) })} />
            </label>
            <label className="cg-sb-ctl">Zoom {scene.zoom.toFixed(2)}×
              <input type="range" className="cg-range" min={options.limits.zoom[0]} max={options.limits.zoom[1]} step="0.05"
                value={scene.zoom} onChange={(e) => onChange({ zoom: Number(e.target.value) })} />
            </label>
            <label className="cg-sb-ctl">Movement
              <select className="cg-select" value={scene.motion} onChange={(e) => onChange({ motion: e.target.value })}>
                {options.motions.map((m) => <option key={m} value={m}>{MOTION[m] || m}</option>)}
              </select>
            </label>
            <label className="cg-sb-ctl">Strength
              <input type="range" className="cg-range" min="0" max="1" step="0.05" value={scene.intensity}
                onChange={(e) => onChange({ intensity: Number(e.target.value) })} />
            </label>
            <label className="cg-sb-ctl">Arrives with
              <select className="cg-select" value={scene.transition} onChange={(e) => onChange({ transition: e.target.value })}>
                {options.transitions.map((t) => <option key={t} value={t}>{TRANSITION[t] || t}</option>)}
              </select>
            </label>
          </div>
          <p className="cg-text-xs cg-text-muted">
            {selected ? 'Click the photo on the left to choose where this scene looks.' : 'Select this scene, then click the photo to choose where it looks.'}
          </p>

          <label className="cg-sb-ctl">Camera
            <textarea className="cg-input" rows={2} maxLength={300} value={scene.camera}
              onChange={(e) => onChange({ camera: e.target.value })} />
          </label>
          <label className="cg-sb-ctl">What it shows
            <textarea className="cg-input" rows={2} maxLength={300} value={scene.detail}
              onChange={(e) => onChange({ detail: e.target.value })} />
          </label>

          <label className="cg-sb-ctl">Prompt for an external AI video tool
            <textarea className="cg-input cg-sb-prompt" rows={6} maxLength={options.limits.scene_prompt} value={scene.prompt}
              onChange={(e) => onChange({ prompt: e.target.value })} />
          </label>
          <div className="cg-caption-actions">
            <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" onClick={onRebuildPrompt}>
              Rebuild prompt from the fields above
            </button>
            <button type="button" className="cg-btn cg-btn--primary cg-btn--sm" onClick={onCopy}>
              {copied ? '✓ Copied' : 'Copy prompt'}
            </button>
          </div>
        </div>
      </div>
    </article>
  );
}
