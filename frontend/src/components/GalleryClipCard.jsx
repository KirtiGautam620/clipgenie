import { useState } from 'react';
import './GalleryClipCard.css';

function moodClass(mood) {
  const m = (mood || 'other').toLowerCase();
  const valid = ['motivational','emotional','funny','educational','spiritual','other'];
  return valid.includes(m) ? m : 'other';
}

export default function GalleryClipCard({ jobId, clip, onEdit, onExport, onUpdated }) {
  const base = `/api/jobs/${jobId}/clips/${clip.id}`;
  const [playing, setPlaying] = useState(false);

  const mood = clip.mood && clip.mood !== 'other' ? clip.mood : null;
  const needsDecision = !!clip.text?.needs_decision;
  const textChip = { headline: 'Headline', none: 'No text' }[clip.text?.mode];
  const mc = moodClass(clip.mood);

  return (
    <article
      className={`cg-gallery-card cg-card cg-card--interactive ${clip.confirmed ? 'cg-gallery-card--confirmed' : ''}`}
      aria-label={`Clip ${clip.id}: ${clip.title || `Clip ${clip.id}`}`}
    >
      {/* Confirmed badge */}
      {clip.confirmed && (
        <span className="cg-gallery-card-confirmed-badge" aria-label="Downloaded and confirmed">✓</span>
      )}

      {/* Video preview */}
      <div className="cg-gallery-video-wrap">
        <video
          className="cg-gallery-video"
          src={`${base}.mp4?v=${clip.version || 0}#t=0.5`}
          controls
          preload="metadata"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          aria-label={`Preview of ${clip.title || `Clip ${clip.id}`}`}
        />
        {!playing && (
          <div className="cg-gallery-video-overlay" aria-hidden="true">
            <span className="cg-gallery-play-hint">▶</span>
          </div>
        )}
        <span className="cg-gallery-duration">{Math.round(clip.duration)}s</span>
      </div>

      {/* Metadata */}
      <div className="cg-gallery-meta">
        <h3 className="cg-gallery-title">{clip.title || `Clip ${clip.id}`}</h3>
        <div className="cg-gallery-chips">
          {mood && (
            <span className={`cg-badge cg-badge--${mc}`}>{mood}</span>
          )}
          {needsDecision && (
            <span className="cg-badge cg-badge--warning" title={clip.text.reasons?.join(' ')}>Needs your decision</span>
          )}
          {textChip && <span className="cg-badge cg-badge--muted">{textChip}</span>}
          {clip.score && !needsDecision && (
            <span className="cg-badge cg-badge--score" title="AI quality score">★ {clip.score}/10</span>
          )}
        </div>
        {clip.reason && (
          <p className="cg-gallery-reason">{clip.reason}</p>
        )}
        {needsDecision && (
          <p className="cg-gallery-reason">
            The speech could not be trusted, so no words are shown. Choose a headline or export without text.
          </p>
        )}
      </div>

      {/* Music indicator */}
      {clip.music && (
        <div className="cg-gallery-music">
          <span className="cg-gallery-music-icon" aria-hidden="true">♪</span>
          <span className="cg-text-sm cg-text-secondary">{clip.music.title}</span>
        </div>
      )}

      {/* Actions */}
      <div className="cg-gallery-actions">
        <button
          className="cg-btn cg-btn--secondary cg-btn--sm"
          onClick={() => onEdit(clip)}
          title="Open in the editor"
        >
          Edit
        </button>
        <button
          className="cg-btn cg-btn--primary cg-btn--sm"
          onClick={() => (needsDecision || !onExport ? onEdit(clip) : onExport(clip))}
          title={needsDecision ? 'Choose how text appears before exporting' : 'Export / Download'}
        >
          {needsDecision ? 'Choose text' : 'Export'}
        </button>
      </div>

      {/* Warnings */}
      {clip.warnings?.length > 0 && (
        <div className="cg-gallery-warnings">
          {clip.warnings.map((w) => (
            <div key={w} className="cg-alert cg-alert--warn">
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}
