import React, { useEffect, useState } from 'react';

const EXAMPLE = 'Create a cinematic UGC video of this product with different camera angles, close-ups, and smooth transitions.';

export default function StoryboardCreate({ options, busy, error, onCreate }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState('');
  const [prompt, setPrompt] = useState('');
  const [product, setProduct] = useState('');
  const [style, setStyle] = useState('');            // '' = decide from the prompt
  const [count, setCount] = useState('');            // '' = decide from the prompt
  const [aspect, setAspect] = useState('9:16');
  const [rights, setRights] = useState('unsure');
  const [people, setPeople] = useState('none');
  const [localError, setLocalError] = useState('');
  const limitMb = options.limits.upload_mb;

  useEffect(() => {
    if (!file) { setPreview(''); return undefined; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function choose(e) {
    const f = e.target.files?.[0];
    setLocalError('');
    if (f && f.size > limitMb * 1024 * 1024) {
      setLocalError(`This photo is larger than ${limitMb} MB.`);
      setFile(null);
      return;
    }
    setFile(f || null);
  }

  function submit(e) {
    e.preventDefault();
    if (!file) return;
    const form = new FormData();
    form.append('photo', file);
    form.append('prompt', prompt);
    form.append('product', product);
    form.append('style', style);
    form.append('count', count);
    form.append('aspect', aspect);
    form.append('rights', rights);
    form.append('people', people);
    onCreate(form);
  }

  const [lo, hi] = options.limits.scenes;
  const counts = Array.from({ length: hi - lo + 1 }, (_, i) => lo + i);

  return (
    <form className="cg-card cg-sb-create" onSubmit={submit}>
      <h1 className="cg-heading-lg">🎞️ Storyboard</h1>
      <p className="cg-text-sm cg-text-secondary">
        Upload one photo and describe the video you want. ClipGenie builds a <strong>shot plan</strong> from
        templates and the words in your prompt, with preview frames cropped from <strong>your own photo</strong>,
        and a prompt for each scene to paste into an external video generator.
      </p>
      <p className="cg-text-xs cg-text-muted">
        It does not generate images or video. The frames show framing and zoom, not new camera angles.
      </p>

      <div className="cg-field">
        <label className="cg-label" htmlFor="sb-photo">Photo</label>
        <input id="sb-photo" type="file" accept="image/jpeg,image/png,image/webp" onChange={choose} />
        <p className="cg-text-xs cg-text-muted">JPG, PNG or WebP, up to {limitMb} MB. Location data is removed.</p>
        {preview && <img className="cg-sb-thumb" src={preview} alt="Your photo" />}
      </div>

      <div className="cg-field">
        <label className="cg-label" htmlFor="sb-prompt">Describe the video</label>
        <textarea id="sb-prompt" className="cg-input" rows={3} maxLength={options.limits.prompt} value={prompt}
          placeholder={EXAMPLE} onChange={(e) => setPrompt(e.target.value)} />
        <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" onClick={() => setPrompt(EXAMPLE)}>
          Use the example
        </button>
      </div>

      <div className="cg-field">
        <label className="cg-label" htmlFor="sb-product">What is in the photo? (optional)</label>
        <input id="sb-product" className="cg-input" maxLength={200} value={product}
          placeholder="e.g. a stainless steel water bottle" onChange={(e) => setProduct(e.target.value)} />
        <p className="cg-text-xs cg-text-muted">ClipGenie cannot see your photo. Say what it shows and it goes into every prompt.</p>
      </div>

      <div className="cg-field">
        <span className="cg-label">Style</span>
        <div className="cg-sb-chips" role="radiogroup" aria-label="Style">
          <button type="button" role="radio" aria-checked={style === ''}
            className={`cg-sb-chip ${style === '' ? 'active' : ''}`} onClick={() => setStyle('')}>From my prompt</button>
          {options.styles.map((s) => (
            <button key={s.id} type="button" role="radio" aria-checked={style === s.id}
              className={`cg-sb-chip ${style === s.id ? 'active' : ''}`} onClick={() => setStyle(s.id)}>{s.label}</button>
          ))}
        </div>
      </div>

      <div className="cg-sb-row">
        <div className="cg-field">
          <label className="cg-label" htmlFor="sb-count">Scenes</label>
          <select id="sb-count" className="cg-select" value={count} onChange={(e) => setCount(e.target.value)}>
            <option value="">From my prompt (default 6)</option>
            {counts.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
        <div className="cg-field">
          <label className="cg-label" htmlFor="sb-aspect">Shape</label>
          <select id="sb-aspect" className="cg-select" value={aspect} onChange={(e) => setAspect(e.target.value)}>
            <option value="9:16">Vertical 9:16</option>
            <option value="16:9">Horizontal 16:9</option>
          </select>
        </div>
      </div>

      <fieldset className="cg-sb-rights">
        <legend className="cg-label">About this photo</legend>
        <div className="cg-sb-row">
          <div className="cg-field">
            <label className="cg-label" htmlFor="sb-rights">Do you have the right to use it?</label>
            <select id="sb-rights" className="cg-select" value={rights} onChange={(e) => setRights(e.target.value)}>
              {options.rights.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
            </select>
          </div>
          <div className="cg-field">
            <label className="cg-label" htmlFor="sb-people">People in the photo</label>
            <select id="sb-people" className="cg-select" value={people} onChange={(e) => setPeople(e.target.value)}>
              {options.people.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
          </div>
        </div>
        <p className="cg-text-xs cg-text-muted">
          Prompts and the download stay locked until you confirm this. If you upload the photo to another tool,
          that tool's terms apply, and anyone who is recognisable in it should have agreed.
        </p>
      </fieldset>

      {(localError || error) && <p className="cg-caption-error" role="alert">{localError || error}</p>}
      <div className="cg-caption-actions">
        <button type="submit" className="cg-btn cg-btn--primary" disabled={!file || busy}>
          {busy ? 'Building…' : 'Build storyboard'}
        </button>
      </div>
    </form>
  );
}
