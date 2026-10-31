import './Dashboard.css';

export default function Dashboard({ health, musicCount, lastJobStatus, onImport, onResume }) {
  const serverDown = health?.status === 'down';
  const ollamaDown = health && !serverDown && !health?.ollama?.running;
  const modelMissing = health?.ollama?.running && !health?.ollama?.model_installed;

  return (
    <main className="cg-main cg-main--centered cg-dashboard">
      {/* Hero */}
      <div className="cg-dashboard-hero">
        <div className="cg-dashboard-logo-glow" aria-hidden="true">🎬</div>
        <h1 className="cg-heading-xl">
          Turn your video into&nbsp;
          <span className="cg-gradient-text">Shorts.</span>
        </h1>
        <p className="cg-dashboard-tagline cg-text-secondary">
          Locally. Privately. Powered by AI on your Mac.
        </p>

        <button
          className="cg-btn cg-btn--primary cg-btn--lg cg-dashboard-cta"
          onClick={onImport}
          disabled={serverDown}
        >
          <span>Import Video</span>
          <span>→</span>
        </button>

        {serverDown && (
          <div className="cg-alert cg-alert--error cg-dashboard-alert" role="alert">
            <span className="cg-alert-icon">⚠️</span>
            <span>
              Cannot reach the ClipGenie server. Make sure it's running with&nbsp;
              <code className="cg-code">./run.sh</code>
            </span>
          </div>
        )}

        {ollamaDown && !serverDown && (
          <div className="cg-alert cg-alert--warn cg-dashboard-alert" role="status">
            <span className="cg-alert-icon">⚡</span>
            <span>
              Ollama isn't running — clips will use the basic picker instead of AI.
              Start it with <code className="cg-code">ollama serve</code>
            </span>
          </div>
        )}

        {modelMissing && !serverDown && (
          <div className="cg-alert cg-alert--warn cg-dashboard-alert" role="status">
            <span className="cg-alert-icon">⚡</span>
            <span>
              AI model not installed. Run&nbsp;
              <code className="cg-code">ollama pull {health.ollama.model}</code>
            </span>
          </div>
        )}
      </div>

      {/* Resume session card */}
      {lastJobStatus === 'done' && (
        <button className="cg-card cg-card--interactive cg-dashboard-resume" onClick={onResume}>
          <div className="cg-dashboard-resume-left">
            <span className="cg-dashboard-resume-icon">↩</span>
            <div>
              <p className="cg-dashboard-resume-label">Resume last session</p>
              <p className="cg-text-sm cg-text-muted">Clips ready — jump back in</p>
            </div>
          </div>
          <span className="cg-text-sm cg-text-secondary">View clips →</span>
        </button>
      )}

      {lastJobStatus && lastJobStatus !== 'done' && lastJobStatus !== 'error' && (
        <button className="cg-card cg-card--interactive cg-dashboard-resume" onClick={onResume}>
          <div className="cg-dashboard-resume-left">
            <span className="cg-spinner" aria-hidden="true" />
            <div>
              <p className="cg-dashboard-resume-label">Job in progress</p>
              <p className="cg-text-sm cg-text-muted">Click to watch the progress</p>
            </div>
          </div>
          <span className="cg-text-sm cg-text-secondary">View →</span>
        </button>
      )}

      {/* Feature pills */}
      <div className="cg-dashboard-features" aria-hidden="true">
        {[
          ['🎙', 'AI transcription'],
          ['✂️', 'Smart clip selection'],
          ['📱', '9:16 vertical output'],
          ['🎵', 'Mood-matched music'],
          ['💬', 'Animated captions'],
          ['🔒', 'Fully local'],
        ].map(([icon, label]) => (
          <span key={label} className="cg-dashboard-feature-pill">
            {icon} {label}
          </span>
        ))}
      </div>
    </main>
  );
}

