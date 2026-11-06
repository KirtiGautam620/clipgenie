import { LogoMark, Panda } from './Botanicals.jsx';
import './ProcessingScreen.css';

const STEPS = [
  { key: 'uploading',    label: 'Uploading',          icon: '⬆', desc: 'Sending your video to the server' },
  { key: 'downloading',  label: 'Downloading',         icon: '⬇', desc: 'Fetching video from YouTube' },
  { key: 'transcribing', label: 'Listening',           icon: '🎙', desc: 'AI transcribing the audio' },
  { key: 'choosing',     label: 'Finding moments',     icon: '✨', desc: 'AI picking the best highlights' },
  { key: 'exporting',    label: 'Editing clips',       icon: '✂️', desc: 'Cutting, captioning & mixing music' },
];

function stepState(stepKey, currentStatus) {
  const order = STEPS.map((s) => s.key);
  const stepIdx = order.indexOf(stepKey);
  const currIdx = order.indexOf(currentStatus);
  if (currIdx < 0) return 'pending';
  if (stepIdx < currIdx) return 'done';
  if (stepIdx === currIdx) return 'active';
  return 'pending';
}

export default function ProcessingScreen({ job, source, onNewVideo }) {
  const status = job?.status || 'uploading';

  // Filter out "downloading" step unless we're actually downloading (URL source)
  const visibleSteps = STEPS.filter(
    (s) => s.key !== 'downloading' || source === 'url' || status === 'downloading'
  );

  const isError = status === 'error';
  const activeStep = visibleSteps.find((s) => s.key === status);

  return (
    <main className="cg-main cg-main--centered cg-processing">
      <div className="cg-processing-card cg-card">
        {isError ? (
          <>
            <Panda width={88} pose="worried" />
            <h1 className="cg-heading-md">Something went wrong</h1>
            <p className="cg-text-secondary cg-text-sm" style={{ maxWidth: 400, textAlign: 'center' }}>
              {job?.error || 'An unexpected error occurred. Please try again.'}
            </p>
            <button className="cg-btn cg-btn--primary" onClick={onNewVideo}>
              Try another video
            </button>
          </>
        ) : (
          <>
            {/* Active step hero */}
            <div className="cg-processing-hero" aria-live="polite">
              <div className="cg-processing-pulse" aria-hidden="true">
                <span className="cg-processing-pulse-icon">
                  <Panda width={52} pose="working" />
                </span>
              </div>
              <h1 className="cg-heading-md cg-processing-status">
                {activeStep?.desc || 'Working on your video…'}
              </h1>
              {job?.progress && (
                <span className="cg-badge cg-badge--accent cg-processing-progress">
                  {job.progress}
                </span>
              )}
              {status === 'queued' && (
                <p className="cg-text-sm cg-text-muted">Waiting for another job to finish…</p>
              )}
            </div>

            {/* Step pipeline */}
            <div className="cg-processing-pipeline" role="list" aria-label="Processing steps">
              {visibleSteps.map((step, i) => {
                const state = stepState(step.key, status);
                return (
                  <div key={step.key} className="cg-pipeline-item" role="listitem">
                    <div className={`cg-pipeline-node cg-pipeline-node--${state}`} aria-hidden="true">
                      {state === 'done' && <span>✓</span>}
                      {state === 'active' && <span className="cg-pipeline-spin" />}
                    </div>
                    {i < visibleSteps.length - 1 && (
                      <div className={`cg-pipeline-line ${state === 'done' ? 'cg-pipeline-line--done' : ''}`} aria-hidden="true" />
                    )}
                    <p className={`cg-pipeline-label cg-pipeline-label--${state}`}>
                      {step.label}
                    </p>
                  </div>
                );
              })}
            </div>

            <p className="cg-text-sm cg-text-muted cg-processing-hint">
              Long videos can take several minutes. You can leave this tab open.
            </p>

            <button className="cg-btn cg-btn--ghost cg-btn--sm" onClick={onNewVideo}>
              Start a different video
            </button>
          </>
        )}
      </div>
    </main>
  );
}

