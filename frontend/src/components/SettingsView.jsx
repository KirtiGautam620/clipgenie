import React, { useState } from 'react';
import { Panda } from './Botanicals.jsx';
import './SettingsView.css';

export default function SettingsView({ health, musicCount = 0 }) {
  const [cleared, setCleared] = useState(false);

  const handleClearCache = () => {
    try {
      localStorage.removeItem('clipgenie.lastJob');
      setCleared(true);
      setTimeout(() => setCleared(false), 2000);
    } catch {
      // ignore
    }
  };

  const ollamaOk = health?.ollama?.running && health?.ollama?.model_installed;
  const ffmpegOk = health?.ffmpeg;

  return (
    <div className="cg-settings-page">
      <div className="cg-settings-header">
        <div>
          <h1 className="cg-heading-lg">Studio Settings & Diagnostics</h1>
          <p className="cg-text-secondary cg-text-sm" style={{ marginTop: 4 }}>
            System configuration, local AI models, and storage cache controls.
          </p>
        </div>
        <Panda width={72} className="cg-page-panda" pose="working" />
      </div>

      <div className="cg-settings-container">
        {/* 0. Mac protection: disk space and memory, so a video never overloads the Mac */}
        {health?.system && (
          <section className="cg-card cg-settings-card">
            <h2 className="cg-heading-sm">Mac Protection</h2>
            <p className="cg-text-xs cg-text-muted">
              CocoGenie checks your Mac before it starts a video. It only reads these numbers and changes nothing.
            </p>
            <div className="cg-settings-item">
              <div className="cg-settings-info">
                <span className="cg-settings-label">Free disk space</span>
                <span className="cg-text-xs cg-text-muted">{health.system.disk_free_gb} GB free</span>
              </div>
              <span className={`cg-badge ${health.system.disk_free_gb >= 15 ? 'cg-badge--success' : health.system.disk_free_gb >= 5 ? 'cg-badge--warning' : 'cg-badge--error'}`}>
                {health.system.disk_free_gb >= 15 ? 'Plenty' : health.system.disk_free_gb >= 5 ? 'Getting low' : 'Too low'}
              </span>
            </div>
            <div className="cg-settings-item">
              <div className="cg-settings-info">
                <span className="cg-settings-label">Memory</span>
                <span className="cg-text-xs cg-text-muted">
                  {health.system.memory_free_pct != null ? `${health.system.memory_free_pct}% free` : 'Not available'}
                  {health.system.swap_used_mb != null && ` · swap in use ${Math.round(health.system.swap_used_mb / 1024 * 10) / 10} GB`}
                </span>
              </div>
              <span className={`cg-badge ${health.system.messages.length === 0 ? 'cg-badge--success' : 'cg-badge--warning'}`}>
                {health.system.messages.length === 0 ? 'Fine' : 'Busy'}
              </span>
            </div>
            {health.system.messages.map((m) => (
              <div key={m} className={`cg-alert ${health.system.level === 'block' ? 'cg-alert--error' : 'cg-alert--warn'}`} role="status">
                <span>{m}</span>
              </div>
            ))}
          </section>
        )}

        {/* 1. Local AI Diagnostics */}
        <section className="cg-card cg-settings-card">
          <h2 className="cg-heading-sm">Local AI Engine Status</h2>
          <p className="cg-text-xs cg-text-muted">
            CocoGenie executes 100% locally on your Apple Silicon Mac without cloud APIs.
          </p>

          <div className="cg-settings-item">
            <div className="cg-settings-info">
              <span className="cg-settings-label">Ollama Local LLM Server</span>
              <span className="cg-text-xs cg-text-muted">
                Picks the most engaging moments in your video.
              </span>
            </div>
            <span className={`cg-badge ${ollamaOk ? 'cg-badge--success' : 'cg-badge--warning'}`}>
              {ollamaOk ? `Active (${health.ollama.model})` : 'Offline (Start with: ollama serve)'}
            </span>
          </div>

          <div className="cg-settings-item">
            <div className="cg-settings-info">
              <span className="cg-settings-label">Whisper MLX Transcription</span>
              <span className="cg-text-xs cg-text-muted">
                Turns speech into text with the time of each word, on this Mac (Apple Silicon).
              </span>
            </div>
            <span className="cg-badge cg-badge--muted">Runs on this Mac</span>
          </div>

          <div className="cg-settings-item">
            <div className="cg-settings-info">
              <span className="cg-settings-label">FFmpeg Video Engine</span>
              <span className="cg-text-xs cg-text-muted">
                Cuts and crops the video to 9:16, draws the text, levels your voice and mixes the music.
              </span>
            </div>
            <span className={`cg-badge ${ffmpegOk ? 'cg-badge--success' : 'cg-badge--error'}`}>
              {ffmpegOk ? 'Binary Found ✓' : 'Missing (brew install ffmpeg)'}
            </span>
          </div>

          <div className="cg-settings-item">
            <div className="cg-settings-info">
              <span className="cg-settings-label">Music library</span>
              <span className="cg-text-xs cg-text-muted">
                Licensed tracks CocoGenie can mix under your videos. Manage them in Music.
              </span>
            </div>
            <span className={`cg-badge ${musicCount > 0 ? 'cg-badge--success' : 'cg-badge--warning'}`}>
              {musicCount} {musicCount === 1 ? 'track' : 'tracks'}
            </span>
          </div>
        </section>

        {/* 2. Storage Cache Management */}
        <section className="cg-card cg-settings-card">
          <h2 className="cg-heading-sm">Local Storage & Cache</h2>
          <p className="cg-text-xs cg-text-muted">
            Videos and temporary rendering frames are stored locally in <code>data/</code> on your Mac.
          </p>

          <div className="cg-settings-item">
            <div className="cg-settings-info">
              <span className="cg-settings-label">Reset Local Session Cache</span>
              <span className="cg-text-xs cg-text-muted">
                Clears saved project pointers from browser storage.
              </span>
            </div>
            <button
              type="button"
              className="cg-btn cg-btn--secondary cg-btn--sm"
              onClick={handleClearCache}
            >
              {cleared ? '✓ Cleared' : 'Purge Session Cache'}
            </button>
          </div>
        </section>

        {/* 3. Legal & Copyright Architecture */}
        <section className="cg-card cg-settings-card">
          <h2 className="cg-heading-sm">Legal Provenance & Copyright</h2>
          <p className="cg-text-xs cg-text-muted">
            Short clips are not automatically copyright-free. CocoGenie generates cryptographically verifiable JSON rights reports alongside every export to safeguard content creators.
          </p>
        </section>
      </div>
    </div>
  );
}

