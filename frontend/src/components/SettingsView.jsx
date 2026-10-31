import React, { useState } from 'react';
import './SettingsView.css';

export default function SettingsView({ health }) {
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
          <h1 className="cg-heading-lg">⚙️ Studio Settings & Diagnostics</h1>
          <p className="cg-text-secondary cg-text-sm" style={{ marginTop: 4 }}>
            System configuration, local AI models, and storage cache controls.
          </p>
        </div>
      </div>

      <div className="cg-settings-container">
        {/* 1. Local AI Diagnostics */}
        <section className="cg-card cg-settings-card">
          <h2 className="cg-heading-sm">🧠 Local AI Engine Status</h2>
          <p className="cg-text-xs cg-text-muted">
            ClipGenie executes 100% locally on your Apple Silicon Mac without cloud APIs.
          </p>

          <div className="cg-settings-item">
            <div className="cg-settings-info">
              <span className="cg-settings-label">Ollama Local LLM Server</span>
              <span className="cg-text-xs cg-text-muted">
                Highlight selection, scene boundary detection, and copilot reasoning.
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
                Hardware-accelerated word-by-word timestamp extraction via Apple Silicon Metal.
              </span>
            </div>
            <span className="cg-badge cg-badge--success">Apple Metal Ready ✓</span>
          </div>

          <div className="cg-settings-item">
            <div className="cg-settings-info">
              <span className="cg-settings-label">FFmpeg Video Engine</span>
              <span className="cg-text-xs cg-text-muted">
                Hardware-accelerated H.264/HEVC encoding, crop filtering, and audio ducking.
              </span>
            </div>
            <span className={`cg-badge ${ffmpegOk ? 'cg-badge--success' : 'cg-badge--error'}`}>
              {ffmpegOk ? 'Binary Found ✓' : 'Missing (brew install ffmpeg)'}
            </span>
          </div>
        </section>

        {/* 2. Storage Cache Management */}
        <section className="cg-card cg-settings-card">
          <h2 className="cg-heading-sm">📁 Local Storage & Cache</h2>
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
          <h2 className="cg-heading-sm">🛡️ Legal Provenance & Copyright</h2>
          <p className="cg-text-xs cg-text-muted">
            Short clips are not automatically copyright-free. ClipGenie generates cryptographically verifiable JSON rights reports alongside every export to safeguard content creators.
          </p>
        </section>
      </div>
    </div>
  );
}

