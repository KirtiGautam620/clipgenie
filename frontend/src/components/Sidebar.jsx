import React from 'react';
import Icon from './Icon.jsx';
import { LogoMark, Sprig } from './Botanicals.jsx';
import './Sidebar.css';

const NAV = [
  { view: 'home', icon: 'home', label: 'Home' },
  { view: 'create', icon: 'create', label: 'Create', also: ['import'] },
  { view: 'gallery', icon: 'videos', label: 'My videos' },
  { view: 'music', icon: 'music', label: 'Music' },
  { view: 'settings', icon: 'settings', label: 'Settings' },
];

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
      {/* Brand */}
      <div className="cg-sidebar-header" onClick={() => onNavigate('home')} role="button" tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onNavigate('home'); }}>
        <LogoMark size={30} />
        <div className="cg-sidebar-logo-text">
          <span className="cg-sidebar-brand">Clip<span className="cg-sidebar-brand-accent">Genie</span></span>
        </div>
      </div>

      {/* Main navigation */}
      <nav className="cg-sidebar-nav">
        {NAV.map((item) => {
          const active = currentView === item.view || item.also?.includes(currentView);
          return (
            <button
              key={item.view}
              type="button"
              className={`cg-sidebar-item ${active ? 'active' : ''}`}
              onClick={() => onNavigate(item.view)}
              aria-current={active ? 'page' : undefined}
            >
              <span className="cg-sidebar-icon"><Icon name={item.icon} /></span>
              <span className="cg-sidebar-label">{item.label}</span>
              {item.view === 'gallery' && clipsCount > 0 && (
                <span className="cg-sidebar-count-badge">{clipsCount}</span>
              )}
              {item.view === 'gallery' && isProcessing && (
                <span className="cg-spinner" style={{ width: 12, height: 12, marginLeft: 'auto' }} />
              )}
            </button>
          );
        })}
      </nav>

      <div className="cg-sidebar-art" aria-hidden="true">
        <Sprig width={92} tone="leaf" />
      </div>

      {/* Local engine health */}
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
