import { useEffect, useRef, useState } from "react";
import { getJSON } from "./api.js";
import ClipCard from "./ClipCard.jsx";
import MusicLibrary from "./MusicLibrary.jsx";

const STEPS = [
  { key: "downloading", label: "Downloading your video" },
  { key: "transcribing", label: "Listening to your video" },
  { key: "choosing", label: "Finding the best moments" },
  { key: "exporting", label: "Editing your clips" },
];

// What the user may declare about the video. Importing from a link needs the first three.
const RIGHTS = [
  { value: "own", label: "I made this video / I own it" },
  { value: "permission", label: "I have the owner's permission to edit and publish it" },
  { value: "licensed", label: "It is public domain, or licensed for reuse (for example CC BY)" },
  { value: "unsure", label: "I am not sure" },
];

const SAVED_JOB = "clipgenie.lastJob";

export default function App() {
  const [source, setSource] = useState("file"); // file | url
  const [file, setFile] = useState(null);
  const [url, setUrl] = useState("");
  const [rights, setRights] = useState("");
  const [language, setLanguage] = useState("auto");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [minLen, setMinLen] = useState(30);
  const [maxLen, setMaxLen] = useState(60);
  const [count, setCount] = useState(5);
  const [useAi, setUseAi] = useState(true);
  const [framing, setFraming] = useState("crop");
  const [musicOn, setMusicOn] = useState(true);
  const [musicVolume, setMusicVolume] = useState(0.6);
  const [library, setLibrary] = useState({ tracks: [], licenses: {}, moods: [] });
  const [health, setHealth] = useState(null);

  const [jobId, setJobId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState(null); // latest status from the server
  const [clips, setClips] = useState([]);
  const [result, setResult] = useState(null); // note, disclaimer, source of the finished job
  const [error, setError] = useState("");
  const timer = useRef(null);

  useEffect(() => () => clearInterval(timer.current), []);

  function loadLibrary() {
    getJSON("/api/music").then(setLibrary).catch(() => {});
  }

  // On first load: read the library and server health, and reopen the last job if there was one.
  useEffect(() => {
    loadLibrary();
    getJSON("/api/health").then(setHealth).catch(() => setHealth({ status: "down" }));
    let saved = null;
    try { saved = localStorage.getItem(SAVED_JOB); } catch { /* storage not available */ }
    if (saved) {
      getJSON(`/api/jobs/${saved}`).then((s) => {
        setJobId(saved);
        setJob(s);
        if (s.status === "done") finish(saved);
        else if (s.status !== "error") { setBusy(true); watch(saved); }
      }).catch(() => {});
    }
  }, []);

  function clipUpdated(updated) {
    setClips((list) => list.map((c) => (c.id === updated.id ? updated : c)));
  }

  function fail(message) {
    clearInterval(timer.current);
    setError(message);
    setBusy(false);
  }

  async function finish(id) {
    const data = await getJSON(`/api/jobs/${id}/clips`);
    setClips(data.clips);
    setResult(data);
    setBusy(false);
  }

  function watch(id) {
    clearInterval(timer.current);
    timer.current = setInterval(async () => {
      try {
        const s = await getJSON(`/api/jobs/${id}`);
        setJob(s);
        if (s.status === "error") return fail(s.error);
        if (s.status === "done") {
          clearInterval(timer.current);
          await finish(id);
        }
      } catch (e) {
        fail(e.message);
      }
    }, 2000);
  }

  async function start(e) {
    e.preventDefault();
    setError("");
    setClips([]);
    setResult(null);
    setJob({ status: source === "url" ? "downloading" : "uploading" });
    setBusy(true);
    try {
      const form = new FormData();
      if (source === "file") form.append("file", file);
      else form.append("url", url);
      form.append("rights", rights);
      form.append("language", language);
      form.append("min_len", minLen);
      form.append("max_len", maxLen);
      form.append("count", count);
      form.append("use_ai", useAi);
      form.append("framing", framing);
      form.append("music_on", musicOn);
      form.append("music_volume", musicVolume);
      const { job_id } = await getJSON(source === "file" ? "/api/upload" : "/api/import-url",
        { method: "POST", body: form });
      setJobId(job_id);
      try { localStorage.setItem(SAVED_JOB, job_id); } catch { /* ignore */ }
      watch(job_id);
    } catch (err) {
      fail(err.message);
    }
  }

  const rightsOptions = source === "url" ? RIGHTS.filter((r) => r.value !== "unsure") : RIGHTS;
  const ready = rights && (source === "file" ? file : url.trim());
  const steps = STEPS.filter((s) => s.key !== "downloading" || source === "url" || job?.status === "downloading");
  const stepIndex = job ? steps.findIndex((s) => s.key === job.status) : -1;

  return (
    <main>
      <h1>🎬 ClipGenie</h1>
      <p className="sub">
        Drop in a long video and get short, captioned, vertical clips. Everything runs on your Mac.
      </p>

      {health && health.status === "down" && (
        <p className="banner">⚠️ Cannot reach the ClipGenie server. Is it running?</p>
      )}
      {health?.ollama && !health.ollama.running && (
        <p className="banner">
          ⚠️ The local AI (Ollama) is not running, so clips will be chosen by a basic method.
          Start it with <code>ollama serve</code> for smarter choices.
        </p>
      )}
      {health?.ollama?.running && !health.ollama.model_installed && (
        <p className="banner">
          ⚠️ The AI model is not installed. Run <code>ollama pull {health.ollama.model}</code>.
        </p>
      )}

      <form onSubmit={start} className="card">
        <div className="tabs">
          <button type="button" className={source === "file" ? "tab on" : "tab"} disabled={busy}
            onClick={() => { setSource("file"); setRights(""); }}>Upload an MP4</button>
          <button type="button" className={source === "url" ? "tab on" : "tab"} disabled={busy}
            onClick={() => { setSource("url"); setRights(""); }}>YouTube link</button>
        </div>

        {source === "file" ? (
          <input type="file" accept="video/mp4" disabled={busy}
            onChange={(e) => setFile(e.target.files[0] || null)} />
        ) : (
          <>
            <input type="url" placeholder="https://www.youtube.com/watch?v=…" value={url}
              disabled={busy} onChange={(e) => setUrl(e.target.value)} />
            <p className="hint">
              Only for videos you own or have permission to use. Public links only. If the
              download does not work, download your video yourself and upload the MP4 instead.
            </p>
          </>
        )}

        <fieldset className="rights" disabled={busy}>
          <legend>Who owns this video? (required)</legend>
          {rightsOptions.map((r) => (
            <label key={r.value}>
              <input type="radio" name="rights" value={r.value} checked={rights === r.value}
                onChange={() => setRights(r.value)} />{" "}{r.label}
            </label>
          ))}
          {rights === "unsure" && (
            <p className="warn">
              ⚠️ You can still make clips to look at, but do not publish them until you have
              confirmed you may use this video.
            </p>
          )}
        </fieldset>

        <label>
          Spoken language{" "}
          <select value={language} onChange={(e) => setLanguage(e.target.value)} disabled={busy}>
            <option value="auto">Detect automatically</option>
            <option value="en">English</option>
            <option value="hi">Hindi / Hinglish</option>
          </select>
        </label>

        <button type="button" className="link" onClick={() => setShowAdvanced(!showAdvanced)}>
          {showAdvanced ? "▾ Hide options" : "▸ More options"}
        </button>
        {showAdvanced && (
          <div className="advanced">
            <div className="row">
              <label>Clip length (seconds){" "}
                <input type="number" value={minLen} min="5" max="180" disabled={busy}
                  onChange={(e) => setMinLen(+e.target.value)} />
                {" – "}
                <input type="number" value={maxLen} min="5" max="180" disabled={busy}
                  onChange={(e) => setMaxLen(+e.target.value)} />
              </label>
              <label>Number of clips{" "}
                <input type="number" value={count} min="1" max="10" disabled={busy}
                  onChange={(e) => setCount(+e.target.value)} />
              </label>
            </div>
            <label>Vertical framing{" "}
              <select value={framing} onChange={(e) => setFraming(e.target.value)} disabled={busy}>
                <option value="crop">Fill the screen (crops the sides, fast)</option>
                <option value="blur">Show the whole picture over a blurred background (slower)</option>
              </select>
            </label>
            <label>
              <input type="checkbox" checked={useAi} disabled={busy}
                onChange={(e) => setUseAi(e.target.checked)} />{" "}
              Use the local AI to choose the best moments
            </label>
            <label>
              <input type="checkbox" checked={musicOn} disabled={busy}
                onChange={(e) => setMusicOn(e.target.checked)} />{" "}
              Add background music that fits each clip's mood
            </label>
            {musicOn && (
              <label>Music volume {Math.round(musicVolume * 100)}%{" "}
                <input type="range" min="0" max="1" step="0.05" value={musicVolume} disabled={busy}
                  onChange={(e) => setMusicVolume(+e.target.value)} />
              </label>
            )}
          </div>
        )}
        <button disabled={!ready || busy}>Create my clips</button>
      </form>

      {busy && job && (
        <section className="card">
          {job.status === "uploading" && <p className="status">⏳ Uploading…</p>}
          {job.status === "queued" && <p className="status">⏳ Waiting for another job to finish…</p>}
          <ol className="steps">
            {steps.map((s, i) => (
              <li key={s.key} className={i < stepIndex ? "done" : i === stepIndex ? "active" : ""}>
                {i < stepIndex ? "✅" : i === stepIndex ? "⏳" : "○"} {s.label}
                {i === stepIndex && job.progress ? ` — ${job.progress}` : ""}
              </li>
            ))}
          </ol>
          <p className="hint">Long videos can take several minutes. You can leave this tab open.</p>
        </section>
      )}
      {error && <p className="error">⚠️ {error}</p>}

      <MusicLibrary library={library} onChanged={loadLibrary} />

      {!busy && result && (
        <section className="card">
          <h2>Your clips</h2>
          <p className="hint">
            Source: {result.source.rights_label}
            {result.source.url ? ` · ${result.source.url}` : ""}
          </p>
          {result.note && result.note !== "ok" && <p className="error">⚠️ {result.note}</p>}
          {clips.length === 0 && <p>No clips found. Try a shorter minimum length.</p>}
          <div className="clips">
            {clips.map((c) => (
              <ClipCard key={c.id} jobId={jobId} clip={c} tracks={library.tracks}
                onUpdated={clipUpdated} />
            ))}
          </div>
          <p className="disclaimer">{result.disclaimer}</p>
        </section>
      )}
    </main>
  );
}
