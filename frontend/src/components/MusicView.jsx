import React from 'react';
import MusicLibraryPanel from './MusicLibraryPanel.jsx';
import './MusicView.css';

export default function MusicView({ library, onLibraryChange }) {
  return (
    <div className="cg-music-view-page">
      <div className="cg-music-view-header">
        <div>
          <h1 className="cg-heading-lg">Music Library</h1>
          <p className="cg-text-secondary cg-text-sm" style={{ marginTop: 4 }}>
            Local audio tracks with automated speech-ducking. Only licensed, copyright-safe audio is used.
          </p>
        </div>
        <span className="cg-badge cg-badge--accent cg-music-count">
          {library.tracks?.length || 0} Tracks Available
        </span>
      </div>

      <div className="cg-card cg-music-view-card">
        <MusicLibraryPanel library={library} onChanged={onLibraryChange} />
      </div>
    </div>
  );
}

