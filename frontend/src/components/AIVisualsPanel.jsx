import React, { useState } from 'react';
import './AIVisualsPanel.css';

const PRESET_CONCEPTS = [
  { id: 'brain', title: 'Neural Brain Synapses', keywords: 'glowing neural network intelligence thoughts', icon: '🧠', tag: 'Science & AI' },
  { id: 'server', title: 'Data Center / Cloud', keywords: 'server racks glowing blue LED tech room', icon: '🖥️', tag: 'Technology' },
  { id: 'crypto', title: 'Blockchain & Finance', keywords: 'golden digital coins futuristic financial chart', icon: '📈', tag: 'Finance' },
  { id: 'space', title: 'Cosmic Nebula Exploration', keywords: 'vibrant stars galaxy space telescope wonder', icon: '✨', tag: 'Discovery' },
  { id: 'nature', title: 'Time-Lapse Mountain Mist', keywords: 'peaceful mountain sunrise cinematic drone shot', icon: '⛰️', tag: 'Atmosphere' },
  { id: 'matrix', title: 'Digital Code Stream', keywords: 'matrix raining code cyber data stream', icon: '💾', tag: 'Coding' },
];

export default function AIVisualsPanel({ onAddVisual, clipTranscript = '' }) {
  const [customPrompt, setCustomPrompt] = useState('');
  const [visualMode, setVisualMode] = useState('pip'); // 'cutaway' | 'pip' | 'split'
  const [selectedPreset, setSelectedPreset] = useState(PRESET_CONCEPTS[0]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [recentGenerated, setRecentGenerated] = useState(PRESET_CONCEPTS);

  const handleGenerate = (e) => {
    e.preventDefault();
    if (!customPrompt.trim()) return;
    setIsGenerating(true);
    // Simulate local generation / asset synthesis
    setTimeout(() => {
      const newVisual = {
        id: `vis-${Date.now()}`,
        title: customPrompt.slice(0, 30),
        keywords: customPrompt,
        icon: '✨',
        tag: 'Custom Generated',
      };
      setRecentGenerated([newVisual, ...recentGenerated]);
      setSelectedPreset(newVisual);
      setIsGenerating(false);
      setCustomPrompt('');
    }, 1200);
  };

  const handleInsert = (preset) => {
    onAddVisual({
      id: `broll-${Date.now()}`,
      title: preset.title,
      type: 'broll',
      mode: visualMode,
      icon: preset.icon,
      start: 2,
      duration: 4,
    });
  };

  return (
    <div className="cg-panel-content">
      <div className="cg-panel-header">
        <h3 className="cg-heading-sm">✨ AI Visuals & B-Roll</h3>
        <span className="cg-badge cg-badge--accent">100% Local</span>
      </div>

      <p className="cg-text-xs cg-text-muted">
        Generate context-aware visual overlays without cloud subscriptions. Runs using local model intelligence.
      </p>

      {/* Visual Placement Mode Selector */}
      <div className="cg-field">
        <label className="cg-label">Placement Style</label>
        <div className="cg-visual-mode-toggle">
          <button
            type="button"
            className={`cg-mode-card ${visualMode === 'pip' ? 'active' : ''}`}
            onClick={() => setVisualMode('pip')}
          >
            <span className="cg-mode-icon">🪟</span>
            <span className="cg-mode-title">PiP Corner</span>
            <span className="cg-text-xs cg-text-muted">Floating inset</span>
          </button>
          <button
            type="button"
            className={`cg-mode-card ${visualMode === 'cutaway' ? 'active' : ''}`}
            onClick={() => setVisualMode('cutaway')}
          >
            <span className="cg-mode-icon">🖼️</span>
            <span className="cg-mode-title">Full Cutaway</span>
            <span className="cg-text-xs cg-text-muted">Covers screen</span>
          </button>
          <button
            type="button"
            className={`cg-mode-card ${visualMode === 'split' ? 'active' : ''}`}
            onClick={() => setVisualMode('split')}
          >
            <span className="cg-mode-icon">⚯</span>
            <span className="cg-mode-title">Split Screen</span>
            <span className="cg-text-xs cg-text-muted">Top & bottom</span>
          </button>
        </div>
      </div>

      {/* Custom Generator Form */}
      <form onSubmit={handleGenerate} className="cg-visual-form">
        <label className="cg-label" htmlFor="broll-prompt">Generate from Speech Topic</label>
        <div className="cg-visual-input-group">
          <input
            id="broll-prompt"
            className="cg-input"
            placeholder="e.g. quantum neural processor glowing..."
            value={customPrompt}
            onChange={(e) => setCustomPrompt(e.target.value)}
            disabled={isGenerating}
          />
          <button
            type="submit"
            className="cg-btn cg-btn--primary cg-btn--sm"
            disabled={!customPrompt.trim() || isGenerating}
          >
            {isGenerating ? <span className="cg-spinner" /> : 'Create'}
          </button>
        </div>
      </form>

      {/* Visual Presets Grid */}
      <div className="cg-field">
        <label className="cg-label">Contextual Visual Candidates</label>
        <div className="cg-visual-grid">
          {recentGenerated.map((item) => (
            <div
              key={item.id}
              className={`cg-visual-card ${selectedPreset?.id === item.id ? 'selected' : ''}`}
              onClick={() => setSelectedPreset(item)}
            >
              <div className="cg-visual-icon-wrap">
                <span className="cg-visual-icon">{item.icon}</span>
              </div>
              <div className="cg-visual-meta">
                <p className="cg-visual-title">{item.title}</p>
                <span className="cg-badge cg-badge--muted cg-text-xs">{item.tag}</span>
              </div>
              <button
                type="button"
                className="cg-btn cg-btn--sm cg-btn--secondary cg-visual-add-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  handleInsert(item);
                }}
                title="Add to Timeline"
              >
                + Add
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

