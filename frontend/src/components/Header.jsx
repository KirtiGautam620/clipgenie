import { LogoMark } from './Botanicals.jsx';
import './Header.css';

export default function Header({ health, musicCount, onLogoClick, currentScreen }) {
  const serverDown = health?.status === 'down';
  // Engine diagnostics (FFmpeg, AI model, music tracks) live in Settings. Only the connection state
  // stays here, because it explains why nothing works.

  // Nothing to say while everything is connected: no empty bar
  if (health && !serverDown) return null;

  return (
    <header className="cg-header">
      {/* Logo */}
      <button className="cg-header-logo" onClick={onLogoClick} aria-label="CocoGenie home">
        <LogoMark size={22} />
        <span className="cg-header-brand">
          Coco<span className="cg-header-brand-accent">Genie</span>
        </span>
      </button>

      <div className="cg-header-spacer" />

      {/* Health pills */}
      <div className="cg-header-nav" role="status" aria-live="polite" aria-label="System status">
        {health === null && (
          <span className="cg-pill cg-pill--warn">
            <span className="cg-pill-dot" />
            Connecting…
          </span>
        )}

        {serverDown && (
          <span className="cg-pill cg-pill--error" title="Cannot reach the CocoGenie server. Is it running?">
            <span className="cg-pill-dot" />
            Server offline
          </span>
        )}

      </div>
    </header>
  );
}

