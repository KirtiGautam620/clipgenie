import React, { useState } from 'react';
import './EffectsTransitionsPanel.css';

const MOTION_EFFECTS = [
  { id: 'zoom-in', title: 'Punch-In Zoom', icon: '🔍', desc: '1.25x scale punch on key statement', defaultDuration: 2.5 },
  { id: 'camera-shake', title: 'Impact Camera Shake', icon: '⚡', desc: 'Dramatic micro-jolt for emphasis', defaultDuration: 0.5 },
  { id: 'smooth-drift', title: 'Smooth Camera Drift', icon: '🎥', desc: 'Subtle slow horizontal push', defaultDuration: 4.0 },
  { id: 'blur-bg', title: 'Cinematic Depth Blur', icon: '🌫️', desc: 'Soft 35px blur on peripheral background', defaultDuration: 5.0 },
  { id: 'glow', title: 'Dreamy Soft Glow', icon: '✨', desc: 'Luminescent diffusion highlights', defaultDuration: 3.0 },
  { id: 'slow-mo', title: 'Speed Retime (0.75x)', icon: '⏳', desc: 'Emotional slow motion emphasis', defaultDuration: 2.0 },
];

const COLOR_GRADES = [
  { id: 'warm', title: 'Warm Podcast Studio', icon: '🌇', filter: 'sepia(15%) saturate(120%) contrast(105%)' },
  { id: 'teal-orange', title: 'Cinematic Teal & Orange', icon: '🎬', filter: 'contrast(125%) saturate(115%) hue-rotate(-10deg)' },
  { id: 'noir', title: 'High-Contrast Noir', icon: '🎞️', filter: 'grayscale(100%) contrast(140%)' },
  { id: 'cyber', title: 'Cyberpunk Neon', icon: '🌆', filter: 'saturate(160%) hue-rotate(20deg) contrast(110%)' },
  { id: 'clean', title: 'Clean Neutral', icon: '⚪', filter: 'none' },
];

const TRANSITIONS = [
  { id: 'whip-pan', title: 'Whip Pan Swipe', icon: '💨', desc: 'Fast motion blur cut to next idea', defaultDuration: 0.4 },
  { id: 'zoom-through', title: 'Zoom Through', icon: '🌀', desc: 'Hyper-punch into the next topic', defaultDuration: 0.5 },
  { id: 'fade-black', title: 'Fade to Black', icon: '🌑', desc: 'Classic cinematic chapter close', defaultDuration: 0.6 },
  { id: 'crossfade', title: 'Smooth Cross Dissolve', icon: '🌓', desc: 'Gentle blend between two thoughts', defaultDuration: 0.8 },
  { id: 'smooth-cut', title: 'Audio J-Cut', icon: '✂️', desc: 'Audio precedes video cut naturally', defaultDuration: 0.3 },
];

export default function EffectsTransitionsPanel({ onAddEffect, onApplyColorGrade, activeFilter = 'none' }) {
  const [activeTab, setActiveTab] = useState('effects'); // 'effects' | 'color' | 'transitions'
  const [selectedEffect, setSelectedEffect] = useState(MOTION_EFFECTS[0]);

  return (
    <div className="cg-panel-content">
      <div className="cg-panel-header">
        <h3 className="cg-heading-sm">🎨 Effects & Transitions</h3>
      </div>

      {/* Subtabs */}
      <div className="cg-tabs">
        <button
          type="button"
          className={`cg-tab ${activeTab === 'effects' ? 'cg-tab--active' : ''}`}
          onClick={() => setActiveTab('effects')}
        >
          Camera FX
        </button>
        <button
          type="button"
          className={`cg-tab ${activeTab === 'color' ? 'cg-tab--active' : ''}`}
          onClick={() => setActiveTab('color')}
        >
          Color Grade
        </button>
        <button
          type="button"
          className={`cg-tab ${activeTab === 'transitions' ? 'cg-tab--active' : ''}`}
          onClick={() => setActiveTab('transitions')}
        >
          Transitions
        </button>
      </div>

      {/* 1. Motion & Camera FX */}
      {activeTab === 'effects' && (
        <div className="cg-effects-list">
          {MOTION_EFFECTS.map((fx) => (
            <div
              key={fx.id}
              className={`cg-effect-card ${selectedEffect?.id === fx.id ? 'selected' : ''}`}
              onClick={() => setSelectedEffect(fx)}
            >
              <div className="cg-effect-icon-wrap">
                <span>{fx.icon}</span>
              </div>
              <div className="cg-effect-meta">
                <p className="cg-effect-title">{fx.title}</p>
                <p className="cg-text-xs cg-text-muted">{fx.desc}</p>
              </div>
              <button
                type="button"
                className="cg-btn cg-btn--sm cg-btn--secondary"
                onClick={(e) => {
                  e.stopPropagation();
                  onAddEffect({
                    id: `fx-${Date.now()}`,
                    title: fx.title,
                    type: 'effects',
                    icon: fx.icon,
                    start: 3,
                    duration: fx.defaultDuration,
                  });
                }}
                title="Add to Timeline"
              >
                + Add
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 2. Color Grading Presets */}
      {activeTab === 'color' && (
        <div className="cg-color-grid">
          {COLOR_GRADES.map((cg) => (
            <div
              key={cg.id}
              className={`cg-color-card ${activeFilter === cg.filter ? 'active' : ''}`}
              onClick={() => onApplyColorGrade(cg.filter)}
            >
              <div className="cg-color-preview-thumb" style={{ filter: cg.filter }}>
                <span className="cg-color-thumb-icon">{cg.icon}</span>
              </div>
              <div className="cg-color-meta">
                <p className="cg-color-title">{cg.title}</p>
                <span className="cg-text-xs cg-text-muted">
                  {activeFilter === cg.filter ? '✓ Applied' : 'Click to apply'}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 3. Transitions */}
      {activeTab === 'transitions' && (
        <div className="cg-effects-list">
          {TRANSITIONS.map((tr) => (
            <div
              key={tr.id}
              className="cg-effect-card"
            >
              <div className="cg-effect-icon-wrap">
                <span>{tr.icon}</span>
              </div>
              <div className="cg-effect-meta">
                <p className="cg-effect-title">{tr.title}</p>
                <p className="cg-text-xs cg-text-muted">{tr.desc}</p>
              </div>
              <button
                type="button"
                className="cg-btn cg-btn--sm cg-btn--secondary"
                onClick={() => {
                  onAddEffect({
                    id: `tr-${Date.now()}`,
                    title: tr.title,
                    type: 'effects',
                    icon: tr.icon,
                    start: 5,
                    duration: tr.defaultDuration,
                  });
                }}
                title="Add to Timeline"
              >
                + Add
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

