import React, { useState, useRef, useEffect } from 'react';
import Timeline from './Timeline.jsx';
import AIVisualsPanel from './AIVisualsPanel.jsx';
import EffectsTransitionsPanel from './EffectsTransitionsPanel.jsx';
import CaptionsStylePanel from './CaptionsStylePanel.jsx';
import AiCopilot from './AiCopilot.jsx';
import ExportStudioModal from './ExportStudioModal.jsx';
import { getJSON } from '../api.js';
import './StudioEditor.css';

const QUICK_PRESETS = [
  { id: 'cinematic', name: 'Cinematic Warm', icon: '🎬', filter: 'contrast(120%) saturate(115%) sepia(10%)' },
  { id: 'vibrant', name: 'Vibrant Tech', icon: '⚡', filter: 'saturate(145%) contrast(115%)' },
  { id: 'noir', name: 'Moody Dramatic', icon: '🎞️', filter: 'grayscale(100%) contrast(135%)' },
  { id: 'clean', name: 'Clean Minimalist', icon: '✨', filter: 'none' },
];

export default function StudioEditor({
  jobId,
  clip: initialClip,
  tracks: musicTracks = [],
  onBack,
  onClipUpdated
}) {
  const [clip, setClip] = useState(initialClip);
  const [mode, setMode] = useState('advanced'); // 'quick' | 'advanced'
  const [leftTab, setLeftTab] = useState('script'); // 'script' | 'broll' | 'effects' | 'captions' | 'audio'
  const [showSafeZones, setShowSafeZones] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(initialClip.duration || 45);
  const [showExportModal, setShowExportModal] = useState(false);

  // Video styling state (simulated real-time preview)
  const [activeFilter, setActiveFilter] = useState('none');
  const [zoomScale, setZoomScale] = useState(1.0);

  // Undo / Redo history stack
  const [history, setHistory] = useState([]);
  const videoRef = useRef(null);

  // Timeline multitrack data model
  const [tracksData, setTracksData] = useState({
    broll: [
      { id: 'broll-1', title: 'AI Concept Visual', start: 2.0, duration: 3.5, mode: 'pip', icon: '🧠' }
    ],
    video: [
      { id: 'vid-1', title: initialClip.title || `Clip #${initialClip.id}`, start: 0, duration: initialClip.duration || 45 }
    ],
    captions: [
      { id: 'cap-1', title: 'Hook Sentence', start: 0.5, duration: 3.5 },
      { id: 'cap-2', title: 'Core Insight', start: 4.5, duration: 6.0 },
      { id: 'cap-3', title: 'Payoff Thought', start: 11.0, duration: 4.0 },
    ],
    music: initialClip.music ? [
      { id: 'mus-1', title: initialClip.music.title, start: 0, duration: initialClip.duration || 45, volume: initialClip.music.volume ?? 0.6 }
    ] : [],
    sfx: [
      { id: 'sfx-1', title: 'Whoosh Punch', start: 0.2, duration: 0.8 },
      { id: 'sfx-2', title: 'Camera Shutter', start: 4.3, duration: 0.6 }
    ],
    effects: [
      { id: 'fx-1', title: 'Punch-In Zoom', start: 1.5, duration: 2.5 }
    ]
  });

  const [selectedItem, setSelectedItem] = useState(tracksData.video[0] || null);

  const base = `/api/jobs/${jobId}/clips/${clip.id}`;

  // Sync video time updates
  const handleTimeUpdate = () => {
    if (videoRef.current) {
      setCurrentTime(videoRef.current.currentTime);
    }
  };

  const handleSeek = (newTime) => {
    setCurrentTime(newTime);
    if (videoRef.current) {
      videoRef.current.currentTime = newTime;
    }
  };

  const handleTogglePlay = () => {
    if (!videoRef.current) return;
    if (isPlaying) {
      videoRef.current.pause();
      setIsPlaying(false);
    } else {
      videoRef.current.play();
      setIsPlaying(true);
    }
  };

  // Push snapshot to undo history
  const pushHistory = (stateSnapshot) => {
    setHistory((prev) => [
      {
        filter: activeFilter,
        zoom: zoomScale,
        tracks: JSON.parse(JSON.stringify(tracksData)),
        ...stateSnapshot
      },
      ...prev.slice(0, 10)
    ]);
  };

  const handleUndo = () => {
    if (history.length === 0) return;
    const [lastState, ...rest] = history;
    if (lastState.filter !== undefined) setActiveFilter(lastState.filter);
    if (lastState.zoom !== undefined) setZoomScale(lastState.zoom);
    if (lastState.tracks !== undefined) setTracksData(lastState.tracks);
    setHistory(rest);
  };

  // Adding visual from AI Panel
  const handleAddVisual = (brollItem) => {
    pushHistory();
    setTracksData((prev) => ({
      ...prev,
      broll: [...prev.broll, brollItem]
    }));
    setSelectedItem(brollItem);
  };

  // Adding effect from Effects Panel
  const handleAddEffect = (fxItem) => {
    pushHistory();
    setTracksData((prev) => ({
      ...prev,
      effects: [...prev.effects, fxItem]
    }));
    setSelectedItem(fxItem);
    if (fxItem.title.toLowerCase().includes('zoom')) {
      setZoomScale(1.2);
    }
  };

  // Color grade applied
  const handleApplyColorGrade = (filterStr) => {
    pushHistory();
    setActiveFilter(filterStr);
  };

  // Copilot action execution
  const handleApplyCopilotAction = (action) => {
    pushHistory();
    if (action.filter) setActiveFilter(action.filter);
    if (action.zoom) setZoomScale(action.zoom);
    if (action.type === 'broll_insert') {
      const newBroll = {
        id: `broll-${Date.now()}`,
        title: 'AI Neural Net',
        start: 1.5,
        duration: 3.5,
        mode: 'pip',
        icon: '🧠'
      };
      setTracksData((prev) => ({
        ...prev,
        broll: [...prev.broll, newBroll]
      }));
    }
  };

  // Quick Preset 1-Click Apply
  const handleApplyQuickPreset = (preset) => {
    pushHistory();
    setActiveFilter(preset.filter);
  };

  // Timeline delete
  const handleDeleteSelected = () => {
    if (!selectedItem) return;
    pushHistory();
    const updated = { ...tracksData };
    for (const key of Object.keys(updated)) {
      updated[key] = updated[key].filter((x) => x.id !== selectedItem.id);
    }
    setTracksData(updated);
    setSelectedItem(null);
  };

  return (
    <div className="cg-studio-shell">
      {/* ── Studio Top Navigation Bar ──────────────────────────────── */}
      <header className="cg-studio-topbar">
        <div className="cg-studio-topbar-left">
          <button className="cg-btn cg-btn--sm cg-btn--ghost" onClick={onBack}>
            ← Gallery
          </button>
          <div className="cg-timeline-divider-v" />
          <span className="cg-studio-project-name">
            <strong>{clip.title || `Clip #${clip.id}`}</strong>
          </span>
          <span className="cg-badge cg-badge--muted">{duration}s</span>
        </div>

        {/* Center: Mode Switcher */}
        <div className="cg-mode-switcher" role="tablist" aria-label="Editing Mode">
          <button
            type="button"
            className={`cg-mode-btn ${mode === 'quick' ? 'active' : ''}`}
            onClick={() => setMode('quick')}
          >
            ⚡ Quick Polish
          </button>
          <button
            type="button"
            className={`cg-mode-btn ${mode === 'advanced' ? 'active' : ''}`}
            onClick={() => setMode('advanced')}
          >
            🎛️ Advanced Studio
          </button>
        </div>

        {/* Right Tools & Export Button */}
        <div className="cg-studio-topbar-right">
          <button
            type="button"
            className={`cg-tool-pill ${showSafeZones ? 'active' : ''}`}
            onClick={() => setShowSafeZones(!showSafeZones)}
            title="Toggle Shorts / Reels Safe Area Guidelines"
          >
            🛡️ Safe Zones
          </button>

          <button
            type="button"
            className="cg-btn cg-btn--sm cg-btn--ghost"
            onClick={handleUndo}
            disabled={history.length === 0}
            title="Undo (⌘Z)"
          >
            ↩ Undo
          </button>

          <button
            type="button"
            className="cg-btn cg-btn--primary cg-btn--sm"
            onClick={() => setShowExportModal(true)}
          >
            Export Short ↓
          </button>
        </div>
      </header>

      {/* ── Main Stage ────────────────────────────────────────────── */}
      {mode === 'quick' ? (
        /* Quick Polish Mode View */
        <main className="cg-quick-mode-container">
          <div className="cg-quick-card">
            <h2 className="cg-heading-md">⚡ 1-Click Aesthetic Presets</h2>
            <p className="cg-text-sm cg-text-muted">
              Select an instant visual theme to polish colors, typography, and pacing simultaneously.
            </p>

            <div className="cg-quick-presets-grid">
              {QUICK_PRESETS.map((qp) => (
                <div
                  key={qp.id}
                  className={`cg-quick-preset-box ${activeFilter === qp.filter ? 'active' : ''}`}
                  onClick={() => handleApplyQuickPreset(qp)}
                >
                  <span className="cg-quick-preset-icon">{qp.icon}</span>
                  <p className="cg-quick-preset-name">{qp.name}</p>
                  <span className="cg-badge cg-badge--muted cg-text-xs">
                    {activeFilter === qp.filter ? '✓ Active' : 'Click to Apply'}
                  </span>
                </div>
              ))}
            </div>

            <div className="cg-quick-actions-row">
              <button
                type="button"
                className="cg-btn cg-btn--secondary"
                onClick={() => setMode('advanced')}
              >
                🎛️ Open in Advanced Studio Timeline →
              </button>
              <button
                type="button"
                className="cg-btn cg-btn--primary"
                onClick={() => setShowExportModal(true)}
              >
                Render & Export ↓
              </button>
            </div>
          </div>
        </main>
      ) : (
        /* Advanced 3-Pane Editing Stage */
        <div className="cg-studio-stage">
          {/* 1. Left Panel (Tools & Assets) */}
          <aside className="cg-left-panel">
            <div className="cg-panel-tabs">
              <button
                type="button"
                className={`cg-panel-tab ${leftTab === 'script' ? 'active' : ''}`}
                onClick={() => setLeftTab('script')}
              >
                📝 Script
              </button>
              <button
                type="button"
                className={`cg-panel-tab ${leftTab === 'broll' ? 'active' : ''}`}
                onClick={() => setLeftTab('broll')}
              >
                ✨ Visuals
              </button>
              <button
                type="button"
                className={`cg-panel-tab ${leftTab === 'effects' ? 'active' : ''}`}
                onClick={() => setLeftTab('effects')}
              >
                🎨 Effects
              </button>
              <button
                type="button"
                className={`cg-panel-tab ${leftTab === 'captions' ? 'active' : ''}`}
                onClick={() => setLeftTab('captions')}
              >
                💬 Captions
              </button>
              <button
                type="button"
                className={`cg-panel-tab ${leftTab === 'audio' ? 'active' : ''}`}
                onClick={() => setLeftTab('audio')}
              >
                🎵 Audio
              </button>
            </div>

            <div className="cg-panel-body">
              {leftTab === 'script' && (
                <div className="cg-panel-content">
                  <div className="cg-panel-header">
                    <h3 className="cg-heading-sm">📝 Script-First Sync</h3>
                    <span className="cg-badge cg-badge--accent">Revid Style</span>
                  </div>
                  <p className="cg-text-xs cg-text-muted">
                    Click any sentence to jump the playhead. Speech and visuals are linked.
                  </p>
                  <div className="cg-script-scenes-list">
                    {[
                      { start: 0, end: 4, text: clip.title || 'The core hook statement begins here.' },
                      { start: 4, end: 12, text: clip.reason || 'An engaging breakthrough insight that keeps retention high.' },
                      { start: 12, end: Math.max(15, duration), text: 'And that is why this moment changes everything you know.' },
                    ].map((scene, idx) => {
                      const isActive = currentTime >= scene.start && currentTime < scene.end;
                      return (
                        <div
                          key={idx}
                          className={`cg-script-scene-card ${isActive ? 'active' : ''}`}
                          onClick={() => handleSeek(scene.start)}
                        >
                          <div className="cg-scene-card-header">
                            <span className="cg-scene-time-tag">
                              {String(scene.start).padStart(2, '0')}:00 – {String(scene.end).padStart(2, '0')}:00
                            </span>
                            {isActive && <span className="cg-badge cg-badge--accent cg-text-xs">Playing</span>}
                          </div>
                          <p className="cg-scene-text">"{scene.text}"</p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
              {leftTab === 'broll' && (
                <AIVisualsPanel
                  onAddVisual={handleAddVisual}
                  clipTranscript={clip.reason}
                />
              )}
              {leftTab === 'effects' && (
                <EffectsTransitionsPanel
                  onAddEffect={handleAddEffect}
                  onApplyColorGrade={handleApplyColorGrade}
                  activeFilter={activeFilter}
                />
              )}
              {leftTab === 'captions' && (
                <CaptionsStylePanel
                  jobId={jobId}
                  clip={clip}
                  onApplied={(updated) => {
                    setClip(updated);
                    if (onClipUpdated) onClipUpdated(updated);
                  }}
                />
              )}
              {leftTab === 'audio' && (
                <div className="cg-panel-content">
                  <h3 className="cg-heading-sm">🎵 Audio Stems & Ducking</h3>
                  <p className="cg-text-xs cg-text-muted">
                    Background music automatically ducks during speech.
                  </p>
                  <div className="cg-field">
                    <label className="cg-label">Library Music Tracks</label>
                    <select
                      className="cg-select"
                      onChange={(e) => {
                        const tr = musicTracks.find((x) => x.id === e.target.value);
                        if (tr) {
                          pushHistory();
                          setTracksData((prev) => ({
                            ...prev,
                            music: [{ id: 'mus-1', title: tr.title, start: 0, duration, volume: 0.6 }]
                          }));
                        }
                      }}
                    >
                      <option value="">Select track...</option>
                      {musicTracks.map((t) => (
                        <option key={t.id} value={t.id}>{t.title} ({t.moods[0]})</option>
                      ))}
                    </select>
                  </div>
                </div>
              )}
            </div>
          </aside>

          {/* 2. Center Stage (9:16 Live Preview Canvas) */}
          <main className="cg-center-stage">
            <div className="cg-viewport-container">
              {/* Main Video Viewport with Live CSS Transform simulation */}
              <video
                ref={videoRef}
                className="cg-viewport-screen"
                src={`${base}.mp4?v=${clip.version || 0}`}
                onTimeUpdate={handleTimeUpdate}
                onLoadedMetadata={(e) => setDuration(e.target.duration || initialClip.duration || 45)}
                style={{
                  filter: activeFilter,
                  transform: `scale(${zoomScale})`,
                  transition: 'transform 200ms ease, filter 200ms ease',
                }}
                playsInline
                preload="metadata"
              />

              {/* PiP AI B-Roll Overlay if active */}
              {tracksData.broll?.some((b) => b.mode === 'pip' && currentTime >= b.start && currentTime <= b.start + b.duration) && (
                <div className="cg-viewport-broll-pip">
                  <div className="cg-broll-pip-content">
                    <span>🧠 AI Visual</span>
                  </div>
                </div>
              )}

              {/* Safe Zones Overlay (Shorts & Reels UI guides) */}
              {showSafeZones && (
                <div className="cg-safe-zones-overlay">
                  <div className="cg-safe-zone-top">Top Profile Margin</div>
                  <div className="cg-safe-zone-right">Like / Share Gutter</div>
                  <div className="cg-safe-zone-bottom">Description & Sound Tag Zone (Do Not Obscure)</div>
                </div>
              )}
            </div>

            {/* Viewport Playback Transport Bar */}
            <div className="cg-transport-bar">
              <button
                type="button"
                className="cg-btn cg-btn--sm cg-btn--ghost"
                onClick={() => handleSeek(Math.max(0, currentTime - 1))}
                title="Back 1 Second (←)"
              >
                ⏪
              </button>

              <button
                type="button"
                className="cg-btn cg-btn--primary cg-btn--sm"
                onClick={handleTogglePlay}
                style={{ minWidth: 70 }}
              >
                {isPlaying ? '⏸' : '▶'}
              </button>

              <button
                type="button"
                className="cg-btn cg-btn--sm cg-btn--ghost"
                onClick={() => handleSeek(Math.min(duration, currentTime + 1))}
                title="Forward 1 Second (→)"
              >
                ⏩
              </button>
            </div>
          </main>

          {/* 3. Right Panel (Inspector & In-Editor AI Copilot) */}
          <aside className="cg-right-panel">
            {/* In-Editor AI Copilot */}
            <AiCopilot
              onApplyPromptAction={handleApplyCopilotAction}
              onUndoAction={handleUndo}
              canUndo={history.length > 0}
            />

            {/* Layer Inspector */}
            <div className="cg-inspector-card">
              <div className="cg-inspector-header">
                <h4 className="cg-heading-sm">Inspector</h4>
                <span className="cg-badge cg-badge--muted">
                  {selectedItem ? selectedItem.title : 'No item selected'}
                </span>
              </div>

              {selectedItem ? (
                <div className="cg-inspector-fields">
                  <div className="cg-field">
                    <label className="cg-label">Scale & Punch-In Zoom</label>
                    <input
                      type="range"
                      min="1.0"
                      max="1.5"
                      step="0.05"
                      value={zoomScale}
                      onChange={(e) => setZoomScale(parseFloat(e.target.value))}
                      className="cg-range"
                    />
                    <span className="cg-text-xs cg-text-secondary">{Math.round(zoomScale * 100)}%</span>
                  </div>

                  <div className="cg-field">
                    <label className="cg-label">Color Grading Filter</label>
                    <select
                      className="cg-select"
                      value={activeFilter}
                      onChange={(e) => setActiveFilter(e.target.value)}
                    >
                      <option value="none">Clean Neutral</option>
                      <option value="contrast(125%) saturate(115%) hue-rotate(-10deg)">Cinematic Teal & Orange</option>
                      <option value="sepia(15%) saturate(120%) contrast(105%)">Warm Podcast Studio</option>
                      <option value="grayscale(100%) contrast(140%)">High-Contrast Noir</option>
                    </select>
                  </div>
                </div>
              ) : (
                <p className="cg-text-xs cg-text-muted">
                  Click on any block in the timeline below to inspect and customize its parameters.
                </p>
              )}
            </div>
          </aside>
        </div>
      )}

      {/* ── Bottom Docked Multi-Track Timeline ─────────────────────── */}
      {mode === 'advanced' && (
        <Timeline
          duration={duration}
          currentTime={currentTime}
          onSeek={handleSeek}
          tracksData={tracksData}
          selectedItemId={selectedItem?.id}
          onSelectItem={setSelectedItem}
          isPlaying={isPlaying}
          onTogglePlay={handleTogglePlay}
          onDeleteSelected={handleDeleteSelected}
        />
      )}

      {/* ── Export Studio Modal ────────────────────────────────────── */}
      {showExportModal && (
        <ExportStudioModal
          jobId={jobId}
          clip={clip}
          onClose={() => setShowExportModal(false)}
          onConfirmed={(updated) => {
            setClip(updated);
            if (onClipUpdated) onClipUpdated(updated);
          }}
        />
      )}
    </div>
  );
}

