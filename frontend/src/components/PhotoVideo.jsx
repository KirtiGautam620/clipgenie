import { useEffect, useState } from 'react';
import { getJSON } from '../api.js';
import SongPartPicker from './SongPartPicker.jsx';
import PhotoVideoEditor from './PhotoVideoEditor.jsx';
import LyricTiming from './LyricTiming.jsx';

// A small preview of a chosen photo; the object URL is freed when the thumbnail goes away.
function Thumb({ file }) {
  const [url, setUrl] = useState('');
  useEffect(() => {
    const u = URL.createObjectURL(file);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [file]);
  return <img className="pv-thumb" src={url} alt="" />;
}
import './PhotoVideo.css';

const MAX_PHOTOS = 30;
const POLL_MS = 2000;
const SHORT_MIN = 30;         // the short is 30 to 60 seconds, from any part of the song
const SHORT_MAX = 60;

// Photos + a song + one line of text per photo -> a vertical video (MVP).
export default function PhotoVideo() {
  const [photos, setPhotos] = useState([]);
  const [song, setSong] = useState(null);
  const [lines, setLines] = useState('');
  const [lyrics, setLyrics] = useState('');
  const [rights, setRights] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [project, setProject] = useState(null);
  const [songUrl, setSongUrl] = useState('');
  const [songSeconds, setSongSeconds] = useState(0);
  const [songStart, setSongStart] = useState(0);
  const [videoSeconds, setVideoSeconds] = useState(SHORT_MAX);

  // Read the song's length in the browser, so the user can choose which part to use.
  useEffect(() => {
    setSongStart(0);
    setSongSeconds(0);
    if (!song) { setSongUrl(''); return undefined; }
    const url = URL.createObjectURL(song);
    const probe = new Audio();
    probe.preload = 'metadata';
    probe.onloadedmetadata = () => setSongSeconds(Number.isFinite(probe.duration) ? probe.duration : 0);
    probe.onerror = () => { setSongSeconds(0); setError('This song could not be read. Try an MP3 or WAV file.'); };
    probe.src = url;
    setSongUrl(url);
    return () => { probe.src = ''; URL.revokeObjectURL(url); };
  }, [song]);

  // Keep checking while the video is being made; stop when it is done or failed.
  useEffect(() => {
    if (!project || !['queued', 'rendering', 'timing'].includes(project.status)) return undefined;
    const timer = setTimeout(async () => {
      try {
        setProject(await getJSON(`/api/photo-videos/${project.id}`));
      } catch (e) {
        setError(e.message);
      }
    }, POLL_MS);
    return () => clearTimeout(timer);
  }, [project]);

  // the same rule as the server: trailing blank lines do not count
  const lineParts = lines.split('\n');
  while (lineParts.length && !lineParts[lineParts.length - 1].trim()) lineParts.pop();
  const lineCount = lineParts.length;
  const tooManyLines = photos.length > 0 && lineCount > photos.length;
  const canMake = photos.length > 0 && song && songSeconds > 0 && rights && !tooManyLines && !busy;

  // Each pick ADDS to the photos already chosen, so you can pick one at a time (in order).
  function addPhotos(files) {
    const incoming = Array.from(files || []);             // copy first: the input is cleared after this
    const room = Math.max(0, MAX_PHOTOS - photos.length);
    setPhotos((prev) => [...prev, ...incoming.slice(0, Math.max(0, MAX_PHOTOS - prev.length))]); // latest list
    setError(incoming.length > room ? `Only ${MAX_PHOTOS} photos can be used. The extra ones were not added.` : '');
  }

  function removePhoto(index) {
    setPhotos((prev) => prev.filter((_, i) => i !== index));
    setError('');
  }

  async function makeVideo(e) {
    e.preventDefault();
    if (!canMake) return;
    setBusy(true);
    setError('');
    try {
      const form = new FormData();
      photos.forEach((p) => form.append('photos', p, p.name));
      form.append('song', song, song.name);
      form.append('lines', lines);
      form.append('lyrics', lyrics);
      form.append('rights', rights ? 'yes' : 'no');
      form.append('song_start', String(songStart));
      form.append('video_seconds', String(videoSeconds));
      setProject(await getJSON('/api/photo-videos', { method: 'POST', body: form }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const done = project?.status === 'done';
  const working = project && ['queued', 'rendering', 'timing'].includes(project.status);

  return (
    <section className="cg-pv" aria-labelledby="pv-title">
      <header className="cg-pv-head">
        <h1 id="pv-title" className="cg-pv-title">Photo video</h1>
        <p className="cg-text-sm cg-text-muted">
          Turn photos and a song into a vertical video. Each photo shows for an equal share of the song,
          with its line of text on top.
        </p>
      </header>

      <form className="cg-pv-form" onSubmit={makeVideo}>
        <div className="cg-pv-field">
          <label className="cg-pv-label" htmlFor="pv-photos">Photos (in order, up to {MAX_PHOTOS})</label>
          <div className="pv-pick">
            <label htmlFor="pv-photos" className="pv-file-btn">Choose photos</label>
            <span className="pv-pick-text">{photos.length ? `${photos.length} chosen` : 'None chosen yet'}</span>
          </div>
          <input id="pv-photos" className="pv-file-input" type="file" accept="image/jpeg,image/png,image/webp" multiple
            onChange={(e) => { addPhotos(e.target.files); e.target.value = ''; }} />
          <span className="cg-text-xs cg-text-muted">
            Select them all at once: in the window, press Command+A (or click the first photo, then Shift-click the last).
            Each pick adds to the list.
          </span>
          {photos.length > 0 && (
            <>
              <div className="pv-list-head">
                <span className="cg-text-xs cg-text-muted">
                  {photos.length} photo{photos.length === 1 ? '' : 's'}, in this order
                </span>
                <button type="button" className="pv-link" onClick={() => { setPhotos([]); setError(''); }}
                  disabled={busy}>Clear all</button>
              </div>
              <ol className="pv-list">
                {photos.map((p, i) => (
                  <li key={`${p.name}-${i}`} className="pv-item">
                    <span className="pv-pos">{i + 1}</span>
                    <Thumb file={p} />
                    <span className="pv-name" title={p.name}>{p.name}</span>
                    <button type="button" className="pv-link pv-remove" onClick={() => removePhoto(i)}
                      disabled={busy} aria-label={`Remove ${p.name}`}>Remove</button>
                  </li>
                ))}
              </ol>
            </>
          )}
        </div>

        <label className="cg-pv-field">
          <span className="cg-pv-label">Song</span>
          <div className="pv-pick">
            <span className="pv-file-btn">Choose song</span>
            <span className="pv-pick-text">{song ? song.name : 'None chosen yet'}</span>
          </div>
          <input className="pv-file-input" type="file" accept=".mp3,.wav,.m4a,.ogg,.flac,.aac,audio/*"
            onChange={(e) => setSong(e.target.files?.[0] || null)} />
          <span className="cg-text-xs cg-text-muted">
            Up to 30 minutes long. Choose the part you want below.
          </span>
        </label>

        {song && songSeconds > 0 && (
          <>
            <label className="cg-pv-field">
              <span className="cg-pv-label">Length of the short: {videoSeconds} seconds</span>
              <input type="range" min={SHORT_MIN} max={SHORT_MAX} step="1" value={videoSeconds} disabled={busy}
                onChange={(e) => setVideoSeconds(Number(e.target.value))} />
              <span className="cg-text-xs cg-text-muted">Between {SHORT_MIN} and {SHORT_MAX} seconds.</span>
            </label>
            <SongPartPicker id="photo-video" songSeconds={songSeconds} start={songStart} onStart={setSongStart}
              minLength={videoSeconds} maxLength={videoSeconds} previewUrl={songUrl} disabled={busy} />
          </>
        )}

        <label className="cg-pv-field">
          <span className="cg-pv-label">Lyrics of the whole song (optional)</span>
          <textarea rows={6} value={lyrics} onChange={(e) => setLyrics(e.target.value)}
            placeholder={'Paste the whole song, one line per line sung.'} />
          <span className="cg-text-xs cg-text-muted">
            The app listens to the song and times each line. Each heard line appears on the video while it is sung,
            and the photos change on lyric lines. You check the times before the video is made. With lyrics, the
            text box below is not used.
          </span>
        </label>

        <label className="cg-pv-field">
          <span className="cg-pv-label">Text for each photo</span>
          <textarea rows={6} value={lines} onChange={(e) => setLines(e.target.value)}
            placeholder={'One line per photo, in the same order.\nA blank line means no text on that photo.'} />
          {tooManyLines && (
            <span className="cg-text-xs cg-text-error">
              {lineCount} lines for {photos.length} photos. Use one line per photo or fewer.
            </span>
          )}
        </label>

        <label className="cg-pv-check">
          <input type="checkbox" checked={rights} onChange={(e) => setRights(e.target.checked)} />
          <span>I have the right to use these photos and this song.</span>
        </label>

        {error && <p className="cg-text-sm cg-text-error" role="alert">{error}</p>}

        <div className="cg-pv-actions">
          <button type="submit" className="cg-btn cg-btn--primary" disabled={!canMake}>
            {busy ? 'Starting…' : 'Make photo video'}
          </button>
        </div>
      </form>

      {project && (
        <div className="cg-pv-result" aria-live="polite">
          {project.status === 'timing' && (
            <p className="cg-text-sm">Listening to the song and timing your lyrics… this can take a few minutes.</p>
          )}
          {working && project.status !== 'timing' && <p className="cg-text-sm">Making your video… this can take a minute.</p>}
          {project.status === 'failed' && (
            <p className="cg-text-sm cg-text-error">The video could not be made. {project.error}</p>
          )}
          {done && (
            <a className="cg-btn cg-btn--secondary" href={`/api/photo-videos/${project.id}/video.mp4`} download>
              Download MP4
            </a>
          )}
        </div>
      )}
      {project?.status === 'timed' && <LyricTiming project={project} onProject={setProject} />}
      {project && !['failed', 'timing', 'timed'].includes(project.status) && (
        <PhotoVideoEditor key={`${project.id}-${project.version || 0}`} project={project} onProject={setProject}
          working={working} />
      )}
    </section>
  );
}
