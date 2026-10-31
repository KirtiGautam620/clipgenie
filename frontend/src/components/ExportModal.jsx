import { useState, useEffect, useRef } from 'react';
import { getJSON } from '../api.js';
import './ExportModal.css';

export default function ExportModal({ jobId, clip, onClose, onConfirmed }) {
  const [ticked, setTicked]   = useState([]);
  const [busy, setBusy]       = useState(false);
  const [error, setError]     = useState('');
  const dialogRef             = useRef(null);
  const base                  = `/api/jobs/${jobId}/clips/${clip.id}`;

  // Trap focus & Escape key
  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    el.focus();
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  function toggle(id) {
    setTicked((t) => t.includes(id) ? t.filter((x) => x !== id) : [...t, id]);
  }

  const allTicked = clip.checklist.every((i) => ticked.includes(i.id));

  async function handleConfirm() {
    setBusy(true);
    setError('');
    try {
      const updated = await getJSON(`${base}/checklist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: ticked }),
      });
      onConfirmed(updated);
      // Trigger browser download
      window.location.href = `${base}/download`;
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  }

  return (
    <div
      className="cg-modal-backdrop"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      role="dialog"
      aria-modal="true"
      aria-label="Copyright checklist before download"
    >
      <div
        className="cg-modal cg-export-modal"
        ref={dialogRef}
        tabIndex={-1}
      >
        <div className="cg-export-modal-header">
          <h2 className="cg-heading-md">📋 Before you download</h2>
          <button
            className="cg-btn cg-btn--icon cg-btn--secondary"
            onClick={onClose}
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <p className="cg-text-sm cg-text-secondary">
          Please confirm each item to download <strong>{clip.title || `Clip ${clip.id}`}</strong>.
        </p>

        <div className="cg-export-checklist" role="group" aria-label="Checklist items">
          {clip.checklist.map((item) => {
            const checked = ticked.includes(item.id);
            return (
              <label
                key={item.id}
                className={`cg-checklist-item ${checked ? 'cg-checklist-item--checked' : ''}`}
              >
                <div className={`cg-checklist-box ${checked ? 'cg-checklist-box--checked' : ''}`} aria-hidden="true">
                  {checked && <span>✓</span>}
                </div>
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggle(item.id)}
                  className="cg-checklist-radio"
                  disabled={busy}
                  aria-label={item.text}
                />
                <span className="cg-checklist-text cg-text-sm">{item.text}</span>
              </label>
            );
          })}
        </div>

        {error && (
          <div className="cg-alert cg-alert--error" role="alert">
            <span className="cg-alert-icon">⚠️</span>
            <span>{error}</span>
          </div>
        )}

        <div className="cg-export-modal-actions">
          <button className="cg-btn cg-btn--secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            className="cg-btn cg-btn--primary"
            onClick={handleConfirm}
            disabled={!allTicked || busy}
          >
            {busy
              ? <><span className="cg-spinner" aria-hidden="true" /> Confirming…</>
              : '↓ Confirm & Download'
            }
          </button>
        </div>

        <p className="cg-text-xs cg-text-muted cg-export-disclaimer">
          Short clips are not automatically copyright-free. ClipGenie cannot check ownership
          or promise that platforms' copyright systems won't flag a clip.
        </p>
      </div>
    </div>
  );
}

