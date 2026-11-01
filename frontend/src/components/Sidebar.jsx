import React from 'react';
import './Sidebar.css';

export default function Sidebar({
  currentView,
  onNavigate,
  health,
  clipsCount = 0,
  isProcessing = false
}) {
  const ollamaOk = health?.ollama?.running && health?.ollama?.model_installed;
  const whisperOk = health?.status !== 'down';

  return (
    <aside className="cg-sidebar" aria-label="Main Application Navigation">
      {/* Brand Header */}
      <div className="cg-sidebar-header" onClick={() => onNavigate('home')} role="button" tabIndex={0}>
        <div className="cg-sidebar-logo-icon">🎬</div>
        <div className="cg-sidebar-logo-text">
          <span className="cg-sidebar-brand">Clip<span className="cg-gradient-text">Genie</span></span>
          <span className="cg-sidebar-badge">STUDIO</span>
        </div>
      </div>

      {/* Main Navigation Links */}
      <nav className="cg-sidebar-nav">
        <button
          type="button"
          className={`cg-sidebar-item ${currentView === 'home' ? 'active' : ''}`}
          onClick={() => onNavigate('home')}
        >
          <span className="cg-sidebar-icon">🏠</span>
          <span className="cg-sidebar-label">Home</span>
        </button>

        <button
          type="button"
          className={`cg-sidebar-item ${currentView === 'create' || currentView === 'import' ? 'active' : ''}`}
          onClick={() => onNavigate('create')}
        >
          <span className="cg-sidebar-icon">✨</span>
          <span className="cg-sidebar-label">Create Short</span>
        </button>

        <button
          type="button"
          className={`cg-sidebar-item ${currentView === 'gallery' ? 'active' : ''}`}
          onClick={() => onNavigate('gallery')}
        >
          <span className="cg-sidebar-icon">📁</span>
          <span className="cg-sidebar-label">My Videos</span>
          {clipsCount > 0 && (
            <span className="cg-sidebar-count-badge">{clipsCount}</span>
          )}
          {isProcessing && (
            <span className="cg-spinner" style={{ width: 12, height: 12, marginLeft: 'auto' }} />
          )}
        </button>

        <button
          type="button"
          className={`cg-sidebar-item ${currentView === 'storyboard' ? 'active' : ''}`}
          onClick={() => onNavigate('storyboard')}
        >
          <span className="cg-sidebar-icon">🎞️</span>
          <span className="cg-sidebar-label">Storyboard</span>
        </button>

        <button
          type="button"
          className={`cg-sidebar-item ${currentView === 'music' ? 'active' : ''}`}
          onClick={() => onNavigate('music')}
        >
          <span className="cg-sidebar-icon">🎵</span>
          <span className="cg-sidebar-label">Music</span>
        </button>

        <button
          type="button"
          className={`cg-sidebar-item ${currentView === 'settings' ? 'active' : ''}`}
          onClick={() => onNavigate('settings')}
        >
          <span className="cg-sidebar-icon">⚙️</span>
          <span className="cg-sidebar-label">Settings</span>
        </button>
      </nav>

      {/* Bottom Local Engine Health */}
      <div className="cg-sidebar-footer">
        <div className="cg-engine-status-box">
          <div className="cg-engine-row">
            <span className={`cg-status-dot ${ollamaOk ? 'ok' : 'warn'}`} />
            <span className="cg-engine-name">Ollama: {ollamaOk ? 'Qwen 2.5 ✓' : 'Offline'}</span>
          </div>
          <div className="cg-engine-row">
            <span className={`cg-status-dot ${whisperOk ? 'ok' : 'error'}`} />
            <span className="cg-engine-name">Whisper: {whisperOk ? 'Apple Metal ✓' : 'Offline'}</span>
          </div>
        </div>
      </div>
    </aside>
  );
}

