import { useEffect, useRef, useState } from 'react';
import { getJSON } from './api.js';
import Sidebar from './components/Sidebar.jsx';
import Header from './components/Header.jsx';
import Dashboard from './components/Dashboard.jsx';
import CreateShortWizard from './components/CreateShortWizard.jsx';
import ProcessingScreen from './components/ProcessingScreen.jsx';
import Gallery from './components/Gallery.jsx';
import StudioEditor from './components/StudioEditor.jsx';
import MusicView from './components/MusicView.jsx';
import StoryboardView from './components/StoryboardView.jsx';
import SettingsView from './components/SettingsView.jsx';
import ExportStudioModal from './components/ExportStudioModal.jsx';
import './styles/global.css';

// ── Screens / Views ─────────────────────────────────────────
// home | create | processing | gallery | studio | storyboard | music | settings
const SAVED_JOB = 'clipgenie.lastJob';

export default function App() {
  // ── Navigation & View State ────────────────────────────
  const [view, setView]             = useState('home');
  const [health, setHealth]         = useState(null);
  const [library, setLibrary]       = useState({ tracks: [], licenses: {}, moods: [] });

  // ── Job State ──────────────────────────────────────────
  const [jobId, setJobId]           = useState(null);
  const [jobStatus, setJobStatus]   = useState(null);
  const [busy, setBusy]             = useState(false);
  const [source, setSource]         = useState('file');
  const [clips, setClips]           = useState([]);
  const [result, setResult]         = useState(null);

  // ── Editor & Modal State ───────────────────────────────
  const [editingClip, setEditingClip]     = useState(null);
  const [exportingClip, setExportingClip] = useState(null);

  const timer = useRef(null);

  // ── Mount Lifecycle: health, music, last job ───────────
  useEffect(() => {
    loadHealth();
    loadLibrary();

    let saved = null;
    try { saved = localStorage.getItem(SAVED_JOB); } catch { /* ignore */ }
    if (saved) {
      getJSON(`/api/jobs/${saved}`).then((s) => {
        setJobId(saved);
        setJobStatus(s);
        if (s.status === 'done') {
          finishJob(saved);
        } else if (s.status !== 'error') {
          setBusy(true);
          setView('processing');
          watchJob(saved);
        }
      }).catch(() => { /* stale job */ });
    }

    return () => clearInterval(timer.current);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function loadHealth() {
    getJSON('/api/health')
      .then(setHealth)
      .catch(() => setHealth({ status: 'down' }));
  }

  function loadLibrary() {
    getJSON('/api/music').then(setLibrary).catch(() => {});
  }

  // ── Polling Pipeline ───────────────────────────────────
  function watchJob(id) {
    clearInterval(timer.current);
    timer.current = setInterval(async () => {
      try {
        const s = await getJSON(`/api/jobs/${id}`);
        setJobStatus(s);
        if (s.status === 'error') {
          clearInterval(timer.current);
          setBusy(false);
        } else if (s.status === 'done') {
          clearInterval(timer.current);
          await finishJob(id);
        }
      } catch {
        clearInterval(timer.current);
        setBusy(false);
      }
    }, 2000);
  }

  async function finishJob(id) {
    try {
      const data = await getJSON(`/api/jobs/${id}/clips`);
      setClips(data.clips);
      setResult(data);
      setBusy(false);
      setView('gallery');
    } catch {
      setBusy(false);
    }
  }

  // ── Start Job (from CreateShortWizard) ─────────────────
  async function handleSubmitJob(opts) {
    const {
      source: src, file, url, rights, language,
      minLen, maxLen, count, useAi, framing, musicOn, musicVol,
    } = opts;

    setSource(src);
    setClips([]);
    setResult(null);
    setJobStatus({ status: src === 'url' ? 'downloading' : 'uploading' });
    setBusy(true);
    setView('processing');

    try {
      const form = new FormData();
      if (src === 'file') form.append('file', file);
      else form.append('url', url);
      form.append('rights', rights);
      form.append('language', language);
      form.append('min_len', minLen);
      form.append('max_len', maxLen);
      form.append('count', count);
      form.append('use_ai', useAi);
      form.append('framing', framing);
      form.append('music_on', musicOn);
      form.append('music_volume', musicVol);

      const endpoint = src === 'file' ? '/api/upload' : '/api/import-url';
      const { job_id } = await getJSON(endpoint, { method: 'POST', body: form });

      setJobId(job_id);
      try { localStorage.setItem(SAVED_JOB, job_id); } catch { /* ignore */ }
      watchJob(job_id);
    } catch (err) {
      setJobStatus({ status: 'error', error: err.message });
      setBusy(false);
    }
  }

  // ── Clip Update Dispatcher ─────────────────────────────
  function handleClipUpdated(updated) {
    setClips((list) => list.map((c) => (c.id === updated.id ? updated : c)));
    if (editingClip?.id === updated.id) setEditingClip(updated);
    if (exportingClip?.id === updated.id) setExportingClip(updated);
  }

  // ── Navigation Handlers ────────────────────────────────
  function handleNavigate(target) {
    if (target === 'gallery' && clips.length === 0 && busy) {
      setView('processing');
    } else {
      setView(target);
    }
  }

  function openStudio(clip) {
    setEditingClip(clip);
    setView('studio');
  }

  function handleResetNewVideo() {
    clearInterval(timer.current);
    setBusy(false);
    setJobId(null);
    setJobStatus(null);
    setClips([]);
    setResult(null);
    setEditingClip(null);
    setExportingClip(null);
    try { localStorage.removeItem(SAVED_JOB); } catch { /* ignore */ }
    setView('create');
  }

  return (
    <div className="cg-app-container">
      {/* ── Persistent Left Sidebar Navigation (Revid-Inspired) ─ */}
      {view !== 'studio' && (
        <Sidebar
          currentView={view}
          onNavigate={handleNavigate}
          health={health}
          clipsCount={clips.length}
          isProcessing={busy}
        />
      )}

      {/* ── Main Application Content Pane ────────────────────── */}
      <div className="cg-app-main-pane">
        {/* Header Bar (shown on standard views) */}
        {view !== 'studio' && (
          <Header
            health={health}
            musicCount={library.tracks?.length || 0}
            onLogoClick={() => handleNavigate('home')}
            currentScreen={view}
          />
        )}

        {/* 1. Home / Dashboard */}
        {view === 'home' && (
          <Dashboard
            health={health}
            musicCount={library.tracks?.length || 0}
            lastJobStatus={jobStatus?.status}
            onImport={() => handleNavigate('create')}
            onResume={() => clips.length > 0 ? handleNavigate('gallery') : (jobStatus && setView('processing'))}
          />
        )}

        {/* 2. Create Short Wizard */}
        {view === 'create' && (
          <CreateShortWizard
            busy={busy}
            onSubmit={handleSubmitJob}
            onCancel={() => handleNavigate('home')}
          />
        )}

        {/* 3. AI Processing Pipeline */}
        {view === 'processing' && (
          <ProcessingScreen
            job={jobStatus}
            source={source}
            onNewVideo={handleResetNewVideo}
          />
        )}

        {/* 4. Shorts Gallery */}
        {view === 'gallery' && (
          <Gallery
            jobId={jobId}
            clips={clips}
            result={result}
            library={library}
            onClipUpdated={handleClipUpdated}
            onEdit={openStudio}
            onExport={(clip) => setExportingClip(clip)}
            onNewVideo={() => handleNavigate('create')}
            onLibraryChange={loadLibrary}
          />
        )}

        {/* 5. Revid-Inspired Studio Editor */}
        {view === 'studio' && editingClip && (
          <StudioEditor
            jobId={jobId}
            clip={editingClip}
            tracks={library.tracks || []}
            onBack={() => setView('gallery')}
            onClipUpdated={handleClipUpdated}
          />
        )}

        {/* The optional Storyboard tool (its own screen and API; the Shorts flow never touches it) */}
        {view === 'storyboard' && <StoryboardView />}

        {/* 6. Music Library */}
        {view === 'music' && (
          <MusicView
            library={library}
            onLibraryChange={loadLibrary}
          />
        )}

        {/* 8. Settings & Diagnostics */}
        {view === 'settings' && (
          <SettingsView
            health={health}
          />
        )}

        {/* Direct Export Modal */}
        {exportingClip && (
          <ExportStudioModal
            jobId={jobId}
            clip={exportingClip}
            onClose={() => setExportingClip(null)}
            onConfirmed={handleClipUpdated}
            onChooseText={(c) => { setExportingClip(null); openStudio(c); }}
          />
        )}
      </div>
    </div>
  );
}
