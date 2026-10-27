import { useState } from "react";
import { getJSON } from "./api.js";

// Lists the music you can use, lets you preview each track, and add your own.
export default function MusicLibrary({ library, onChanged }) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("");
  const [mood, setMood] = useState("other");
  const [license, setLicense] = useState("unknown");
  const [attribution, setAttribution] = useState("");
  const [source, setSource] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function add(e) {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("title", title);
      form.append("moods", mood);
      form.append("license", license);
      form.append("attribution", attribution);
      form.append("source", source);
      await getJSON("/api/music", { method: "POST", body: form });
      setFile(null);
      setTitle("");
      setAttribution("");
      setSource("");
      e.target.reset();
      onChanged();
    } catch (err) {
      setError(err.message);
    }
    setSaving(false);
  }

  return (
    <section className="card">
      <button type="button" className="link" onClick={() => setOpen(!open)}>
        {open ? "▾" : "▸"} Music library ({library.tracks.length} tracks)
      </button>
      {open && (
        <>
          <p className="hint">
            Only music in this library is ever used. Add tracks you made, bought, or that are
            free to use, and record the licence. The starter tracks are simple generated
            placeholders (public domain).
          </p>
          <div className="tracks">
            {library.tracks.map((t) => (
              <div key={t.id} className="track">
                <div>
                  <b>{t.title}</b> · {t.moods.join(", ")} · <span>{t.license_label}</span>
                  {t.attribution && <div className="hint">Credit: {t.attribution}</div>}
                  {t.warning && <div className="error small">⚠️ {t.warning}</div>}
                </div>
                <audio controls preload="none" src={`/api/music/${t.id}/preview`} />
              </div>
            ))}
          </div>

          <form onSubmit={add} className="add-track">
            <h2>Add your own music</h2>
            <input type="file" accept="audio/*" onChange={(e) => setFile(e.target.files[0] || null)} />
            <input placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
            <div className="row">
              <label>Mood{" "}
                <select value={mood} onChange={(e) => setMood(e.target.value)}>
                  {library.moods.map((m) => <option key={m}>{m}</option>)}
                </select>
              </label>
              <label>Licence{" "}
                <select value={license} onChange={(e) => setLicense(e.target.value)}>
                  {Object.entries(library.licenses).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </label>
            </div>
            <input placeholder="Credit to show (needed for CC BY)" value={attribution}
              onChange={(e) => setAttribution(e.target.value)} />
            <input placeholder="Where it came from (website or link)" value={source}
              onChange={(e) => setSource(e.target.value)} />
            {license === "unknown" && (
              <p className="error small">⚠️ With an unknown licence, clips using this track will carry a warning.</p>
            )}
            {error && <p className="error small">⚠️ {error}</p>}
            <button disabled={!file || saving}>{saving ? "Adding…" : "Add track"}</button>
          </form>
        </>
      )}
    </section>
  );
}
