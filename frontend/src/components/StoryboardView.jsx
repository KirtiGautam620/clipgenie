import React, { useCallback, useEffect, useState } from 'react';
import { getJSON } from '../api.js';
import StoryboardCreate from './StoryboardCreate.jsx';
import StoryboardEditor from './StoryboardEditor.jsx';
import './Storyboard.css';

// FastAPI answers "Not Found" for a route it does not have. Here that almost always means the server was
// started before the Storyboard feature existed and has to be restarted.
const OLD_SERVER = "The ClipGenie server doesn't have the Storyboard feature yet: it is probably still running an "
  + 'older version. Stop it (press Ctrl+C in the terminal where you started it), start it again with ./run.sh, '
  + 'then reload this page.';
const explain = (e) => (e.message === 'Not Found' ? OLD_SERVER : e.message);

// The optional Storyboard tool. It lives in its own screen and its own API (/api/storyboards) and
// shares nothing with the Shorts workflow.
export default function StoryboardView() {
  const [options, setOptions] = useState(null);
  const [list, setList] = useState([]);
  const [current, setCurrent] = useState(null);       // the storyboard being edited, as the server sent it
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const loadList = useCallback(() => (
    getJSON('/api/storyboards').then((d) => setList(d.storyboards)).catch((e) => setError(explain(e)))
  ), []);

  useEffect(() => {
    getJSON('/api/storyboard-options').then(setOptions).catch((e) => setError(explain(e)));
    loadList();
  }, [loadList]);

  async function open(id) {
    setError('');
    try {
      setCurrent(await getJSON(`/api/storyboards/${id}`));
    } catch (e) {
      setError(explain(e));
    }
  }

  async function create(form) {
    setBusy(true);
    setError('');
    try {
      setCurrent(await getJSON('/api/storyboards', { method: 'POST', body: form }));
      loadList();
    } catch (e) {
      setError(explain(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id) {
    if (!window.confirm('Delete this storyboard and its photo from this computer?')) return;
    try {
      await getJSON(`/api/storyboards/${id}`, { method: 'DELETE' });
      if (current?.id === id) setCurrent(null);
      loadList();
    } catch (e) {
      setError(explain(e));
    }
  }

  if (!options) {
    return (
      <main className="cg-main cg-storyboard">
        {error ? <p className="cg-caption-error" role="alert">{error}</p> : <p className="cg-text-muted">Loading…</p>}
      </main>
    );
  }

  if (current) {
    return (
      <main className="cg-main cg-storyboard">
        <StoryboardEditor
          key={current.id}
          storyboard={current}
          options={options}
          onSaved={(sb) => { setCurrent(sb); loadList(); }}
          onBack={() => { setCurrent(null); loadList(); }}
          onDelete={() => remove(current.id)}
        />
      </main>
    );
  }

  return (
    <main className="cg-main cg-storyboard">
      <StoryboardCreate options={options} busy={busy} error={error} onCreate={create} />
      {list.length > 0 && (
        <section className="cg-card cg-sb-saved">
          <h2 className="cg-heading-sm">Your storyboards</h2>
          <ul className="cg-sb-saved-list">
            {list.map((s) => (
              <li key={s.id}>
                <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" onClick={() => open(s.id)}>
                  {s.title}
                </button>
                <span className="cg-text-xs cg-text-muted">{s.scenes} scenes · {s.aspect}</span>
                <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" onClick={() => remove(s.id)}
                  aria-label={`Delete ${s.title}`}>Delete</button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
