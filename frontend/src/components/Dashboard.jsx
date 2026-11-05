import Icon from './Icon.jsx';
import { Sprig, LeafTrio } from './Botanicals.jsx';
import './Dashboard.css';

const START_OPTIONS = [
  { id: 'url', icon: 'link', title: 'YouTube link',
    text: 'Paste a link to a talk or podcast you have the rights to use.' },
  { id: 'file', icon: 'upload', title: 'Upload a video',
    text: 'Choose an MP4 or MOV from your Mac. It never leaves your computer.' },
];

export default function Dashboard({
  health, musicCount, lastJobStatus, jobId, clips = [], onImport, onResume, onOpenClip,
}) {
  const serverDown = health?.status === 'down';
  const ollamaDown = health && !serverDown && !health?.ollama?.running;
  const modelMissing = health?.ollama?.running && !health?.ollama?.model_installed;
  const inProgress = lastJobStatus && lastJobStatus !== 'done' && lastJobStatus !== 'error';
  const recent = clips.slice(0, 4);

  return (
    <main className="cg-main cg-dashboard">
      {/* Welcome */}
      <section className="cg-dash-hero">
        <div className="cg-dash-hero-text">
          <p className="cg-dash-eyebrow">Welcome to ClipGenie</p>
          <h1 className="cg-heading-xl">
            Turn long videos into <em>Shorts</em> worth watching.
          </h1>
          <p className="cg-dash-tagline">
            Private and local: ClipGenie finds the best moments, frames the speaker, adds captions
            and music, and keeps everything on your Mac.
          </p>
          <button className="cg-btn cg-btn--primary cg-btn--lg" onClick={() => onImport('file')}
            disabled={serverDown}>
            <span>Create a new video</span>
            <Icon name="arrow" size={16} />
          </button>
        </div>
        <div className="cg-dash-hero-art" aria-hidden="true">
          <Sprig width={150} tone="leaf" />
          <Sprig width={110} tone="leaf" flip />
        </div>
      </section>

      {serverDown && (
        <div className="cg-alert cg-alert--error" role="alert">
          <span>
            Cannot reach the ClipGenie server. Make sure it is running with&nbsp;
            <code className="cg-code">./run.sh</code>
          </span>
        </div>
      )}
      {ollamaDown && !serverDown && (
        <div className="cg-alert cg-alert--warn" role="status">
          <span>
            Ollama isn't running, so clips will use the basic picker instead of AI.
            Start it with <code className="cg-code">ollama serve</code>
          </span>
        </div>
      )}
      {modelMissing && !serverDown && (
        <div className="cg-alert cg-alert--warn" role="status">
          <span>
            The AI model isn't installed. Run&nbsp;
            <code className="cg-code">ollama pull {health.ollama.model}</code>
          </span>
        </div>
      )}

      {/* Start something new */}
      <section>
        <h2 className="cg-dash-section-title">Start something new</h2>
        <div className="cg-dash-start">
          {START_OPTIONS.map((o) => (
            <button key={o.id} type="button" className="cg-dash-start-card" disabled={serverDown}
              onClick={() => onImport(o.id)}>
              <span className="cg-dash-start-icon"><Icon name={o.icon} size={22} /></span>
              <span className="cg-dash-start-title">{o.title}</span>
              <span className="cg-dash-start-text">{o.text}</span>
            </button>
          ))}
          {/* Not available yet: shown honestly, not clickable */}
          <div className="cg-dash-start-card cg-dash-start-card--soon" aria-disabled="true">
            <span className="cg-dash-start-icon"><Icon name="photo" size={22} /></span>
            <span className="cg-dash-start-title">
              Photos to video <span className="cg-dash-soon-tag">Coming soon</span>
            </span>
            <span className="cg-dash-start-text">
              Turn a set of photographs into a video with slow zooms and pans.
            </span>
          </div>
        </div>
      </section>

      {/* Recent projects */}
      <section>
        <div className="cg-dash-section-head">
          <h2 className="cg-dash-section-title">Recent project</h2>
          {recent.length > 0 && (
            <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" onClick={onResume}>
              See all {clips.length} videos
            </button>
          )}
        </div>

        {inProgress && (
          <button className="cg-dash-resume" onClick={onResume}>
            <span className="cg-spinner" aria-hidden="true" />
            <span>
              <strong>A video is being made</strong>
              <span className="cg-text-sm cg-text-muted"> · Click to watch the progress</span>
            </span>
          </button>
        )}

        {recent.length > 0 ? (
          <div className="cg-dash-recent">
            {recent.map((c) => (
              <button key={c.id} type="button" className="cg-dash-thumb" onClick={() => onOpenClip(c)}
                aria-label={`Open ${c.title || `Clip ${c.id}`} in the editor`}>
                <span className="cg-dash-thumb-frame">
                  <video src={`/api/jobs/${jobId}/clips/${c.id}.mp4?v=${c.version || 0}#t=0.5`}
                    preload="metadata" muted playsInline />
                  <span className="cg-dash-thumb-dur">{Math.round(c.duration)}s</span>
                </span>
                <span className="cg-dash-thumb-title">{c.title || `Clip ${c.id}`}</span>
              </button>
            ))}
          </div>
        ) : !inProgress && (
          <div className="cg-dash-empty">
            <LeafTrio />
            <p className="cg-text-sm cg-text-secondary">
              Your finished Shorts will appear here. Nothing yet: start with a link or an upload.
            </p>
          </div>
        )}
      </section>

      {musicCount === 0 && !serverDown && (
        <p className="cg-text-xs cg-text-muted">
          Tip: add a few licensed tracks in the Music library and ClipGenie will mix one under each clip.
        </p>
      )}
    </main>
  );
}
