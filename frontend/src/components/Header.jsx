import './Header.css';

const HEALTH_PILLS = [
  {
    key: 'ffmpeg',
    label: 'FFmpeg',
    check: (h) => h.ffmpeg,
    warnMsg: 'FFmpeg not found',
  },
  {
    key: 'ollama',
    label: (h) => h.ollama?.model_installed
      ? `AI (${h.ollama.model?.split(':')[0] || 'Ollama'})`
      : 'AI',
    check: (h) => h.ollama?.running && h.ollama?.model_installed,
    warnMsg: (h) => h.ollama?.running
      ? `Model not installed — run: ollama pull ${h.ollama?.model}`
      : 'Ollama not running — start with: ollama serve',
  },
];

export default function Header({ health, musicCount, onLogoClick, currentScreen }) {
  const serverDown = health?.status === 'down';

  return (
    <header className="cg-header">
      {/* Logo */}
      <button className="cg-header-logo" onClick={onLogoClick} aria-label="ClipGenie home">
        <span className="cg-header-logo-icon">🎬</span>
        <span>
          Clip<span className="cg-gradient-text">Genie</span>
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
          <span className="cg-pill cg-pill--error" title="Cannot reach the ClipGenie server. Is it running?">
            <span className="cg-pill-dot" />
            Server offline
          </span>
        )}

        {health && !serverDown && HEALTH_PILLS.map((p) => {
          const ok = p.check(health);
          const label = typeof p.label === 'function' ? p.label(health) : p.label;
          const warnMsg = typeof p.warnMsg === 'function' ? p.warnMsg(health) : p.warnMsg;
          return (
            <span
              key={p.key}
              className={`cg-pill ${ok ? 'cg-pill--ok' : 'cg-pill--warn'}`}
              title={ok ? `${label} ready` : warnMsg}
            >
              <span className="cg-pill-dot" />
              {label}
            </span>
          );
        })}

        {health && !serverDown && (
          <span
            className={`cg-pill ${musicCount > 0 ? 'cg-pill--ok' : 'cg-pill--warn'}`}
            title={musicCount > 0 ? `${musicCount} tracks in library` : 'No music tracks — add some in the library'}
          >
            <span className="cg-pill-dot" />
            {musicCount} track{musicCount !== 1 ? 's' : ''}
          </span>
        )}
      </div>
    </header>
  );
}

