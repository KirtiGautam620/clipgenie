import { useEffect, useState } from 'react';
import Icon from './Icon.jsx';
import { Sprig, LeafTrio } from './Botanicals.jsx';
import './Dashboard.css';

// "Last edited 3 days ago": the time comes from the real video file (see useLastEdited)
function ago(date) {
  const minutes = (Date.now() - date.getTime()) / 60000;
  if (minutes < 1.5) return 'just now';
  if (minutes < 60) return `${Math.round(minutes)} min ago`;
  const hours = minutes / 60;
  if (hours < 24) return `${Math.round(hours)} ${Math.round(hours) === 1 ? 'hour' : 'hours'} ago`;
  const days = hours / 24;
  if (days < 7) return `${Math.round(days)} ${Math.round(days) === 1 ? 'day' : 'days'} ago`;
  return `on ${date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}`;
}

/**
 * When each shown video was last written to disk (it changes whenever the video is edited and
 * re-made). Read from the file's own Last-Modified header with a 1-byte range request, so no
 * extra server support and no stored timestamps are needed.
 */
function useLastEdited(jobId, clips) {
  const [times, setTimes] = useState({});
  const key = clips.map((c) => `${c.id}:${c.version || 0}`).join(',');
  useEffect(() => {
    let cancelled = false;
    setTimes({});
    clips.forEach(async (c) => {
      try {
        const res = await fetch(`/api/jobs/${jobId}/clips/${c.id}.mp4?v=${c.version || 0}`,
          { headers: { Range: 'bytes=0-0' } });
        const stamp = res.headers.get('last-modified');
        if (stamp && !cancelled) setTimes((t) => ({ ...t, [c.id]: new Date(stamp) }));
      } catch { /* no timestamp: the card simply omits it */ }
    });
    return () => { cancelled = true; };
  }, [jobId, key]); // eslint-disable-line react-hooks/exhaustive-deps
  return times;
}

export default function Dashboard({
  health, lastJobStatus, jobId, clips = [], onImport, onResume, onOpenClip, onOpenSettings,
}) {
  const [link, setLink] = useState('');
  const serverDown = health?.status === 'down';
  const aiDown = health && !serverDown && !(health?.ollama?.running && health?.ollama?.model_installed);
  const inProgress = lastJobStatus && lastJobStatus !== 'done' && lastJobStatus !== 'error';
  const recent = clips.slice(0, 4);
  const edited = useLastEdited(jobId, recent);

  function submitLink(e) {
    e.preventDefault();
    if (link.trim()) onImport('url', link.trim());
  }

  return (
    <main className="cg-main cg-dashboard">
      {/* Welcome */}
      <section className="cg-dash-hero">
        <div className="cg-dash-hero-text">
          <p className="cg-dash-eyebrow">Welcome to CocoGenie</p>
          <h1 className="cg-heading-xl">
            Turn long videos into <em>Shorts</em> worth watching.
          </h1>
          <p className="cg-dash-tagline">
            CocoGenie finds the best moments in your videos, frames the speaker, and adds captions and music.
          </p>
          <button className="cg-btn cg-btn--primary cg-btn--lg" onClick={() => onImport('file')}
            disabled={serverDown}>
            <span>Create a new video</span>
            <Icon name="arrow" size={16} />
          </button>
        </div>
        <div className="cg-dash-hero-art" aria-hidden="true">
          <Sprig width={140} tone="leaf" />
          <Sprig width={100} tone="leaf" flip />
        </div>
      </section>

      {serverDown && (
        <div className="cg-alert cg-alert--error" role="alert">
          <span>
            CocoGenie can't reach its server. Start it with&nbsp;
            <code className="cg-code">./run.sh</code> and refresh this page.
          </span>
        </div>
      )}
      {aiDown && !serverDown && (
        <div className="cg-alert cg-alert--warn" role="status">
          <span>
            The AI helper isn't ready, so clips will be chosen with a simpler method.{' '}
            <button type="button" className="cg-dash-link" onClick={onOpenSettings}>See Settings</button>
          </span>
        </div>
      )}

      {/* Start something new */}
      <section>
        <h2 className="cg-dash-section-title">Start something new</h2>
        <div className="cg-dash-start">
          <form className="cg-dash-start-card cg-dash-start-card--main" onSubmit={submitLink}>
            <span className="cg-dash-start-icon"><Icon name="link" size={22} /></span>
            <span className="cg-dash-start-title">Paste a YouTube link</span>
            <span className="cg-dash-start-text">
              Turn a talk or podcast you have the rights to use into Shorts.
            </span>
            <div className="cg-dash-link-row">
              <input
                type="url"
                className="cg-input"
                placeholder="https://www.youtube.com/watch?v=…"
                value={link}
                onChange={(e) => setLink(e.target.value)}
                disabled={serverDown}
                aria-label="YouTube link"
              />
              <button type="submit" className="cg-btn cg-btn--primary" disabled={serverDown || !link.trim()}>
                Continue
              </button>
            </div>
          </form>

          <div className="cg-dash-start-card cg-dash-start-card--main">
            <span className="cg-dash-start-icon"><Icon name="upload" size={22} /></span>
            <span className="cg-dash-start-title">Upload a video</span>
            <span className="cg-dash-start-text">Choose an MP4 or MOV file from your computer.</span>
            <button type="button" className="cg-btn cg-btn--primary cg-dash-start-btn" disabled={serverDown}
              onClick={() => onImport('file')}>
              Choose a video
            </button>
          </div>

          {/* Not available yet: shown honestly, not clickable */}
          <div className="cg-dash-start-card cg-dash-start-card--soon" aria-disabled="true">
            <span className="cg-dash-start-icon"><Icon name="photo" size={22} /></span>
            <span className="cg-dash-start-title">Photos to video</span>
            <span className="cg-dash-soon-tag">Coming soon</span>
            <span className="cg-dash-start-text">Turn a set of photographs into a video.</span>
          </div>
        </div>
      </section>

      {/* Recent projects */}
      <section>
        <div className="cg-dash-section-head">
          <h2 className="cg-dash-section-title">Recent projects</h2>
          {clips.length > 0 && (
            <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" onClick={onResume}>
              View all {clips.length} {clips.length === 1 ? 'video' : 'videos'}
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
              <article key={c.id} className="cg-dash-project">
                <button type="button" className="cg-dash-thumb" onClick={() => onOpenClip(c)}
                  aria-label={`Open ${c.title || `Clip ${c.id}`} in the editor`}>
                  <video src={`/api/jobs/${jobId}/clips/${c.id}.mp4?v=${c.version || 0}#t=0.5`}
                    preload="metadata" muted playsInline tabIndex={-1} />
                </button>
                <div className="cg-dash-project-body">
                  <h3 className="cg-dash-project-title">{c.title || `Clip ${c.id}`}</h3>
                  <p className="cg-dash-project-meta">
                    {Math.round(c.duration)}s
                    {edited[c.id] && <span> · Last edited {ago(edited[c.id])}</span>}
                  </p>
                  <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" onClick={() => onOpenClip(c)}>
                    Continue editing
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : !inProgress && (
          <div className="cg-dash-empty">
            <LeafTrio />
            <p className="cg-text-sm cg-text-secondary">
              Your finished videos will appear here. Start with a link or an upload above.
            </p>
          </div>
        )}
      </section>
    </main>
  );
}
