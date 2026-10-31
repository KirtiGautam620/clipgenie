import React, { useState } from 'react';
import './AIVisualsBin.css';

const VISUAL_CATEGORIES = [
  { id: 'all', label: 'All Assets' },
  { id: 'tech', label: 'Technology & AI' },
  { id: 'nature', label: 'Atmosphere & Nature' },
  { id: 'business', label: 'Finance & Growth' },
  { id: 'abstract', label: 'Abstract 3D' },
];

const PRE_INDEXED_ASSETS = [
  { id: 'a1', title: 'Neural Brain Synapses', cat: 'tech', icon: '🧠', prompt: 'glowing neural synapses cyber thoughts', res: '1080x1920' },
  { id: 'a2', title: 'Data Center Racks', cat: 'tech', icon: '🖥️', prompt: 'futuristic blue glowing cloud server farm', res: '1080x1920' },
  { id: 'a3', title: 'Cosmic Galaxy Flight', cat: 'nature', icon: '✨', prompt: 'deep space nebula stars high resolution', res: '1080x1920' },
  { id: 'a4', title: 'Mountain Drone Drift', cat: 'nature', icon: '⛰️', prompt: 'misty morning sunrise alpine peak', res: '1080x1920' },
  { id: 'a5', title: 'Cryptocurrency Surge', cat: 'business', icon: '📈', prompt: 'golden financial bull chart glowing green', res: '1080x1920' },
  { id: 'a6', title: 'Matrix Code Stream', cat: 'abstract', icon: '💾', prompt: 'raining emerald cyber data stream', res: '1080x1920' },
  { id: 'a7', title: 'Robotics Assembly Arm', cat: 'tech', icon: '🤖', prompt: 'industrial precision laser robot welding', res: '1080x1920' },
  { id: 'a8', title: 'Fluid Hologram Mesh', cat: 'abstract', icon: '🔮', prompt: 'iridescent metallic chrome waves 3d render', res: '1080x1920' },
];

export default function AIVisualsBin({ onCreateShortWithVisual }) {
  const [activeCat, setActiveCat] = useState('all');
  const [search, setSearch] = useState('');
  const [assets, setAssets] = useState(PRE_INDEXED_ASSETS);
  const [prompt, setPrompt] = useState('');
  const [generating, setGenerating] = useState(false);

  const filtered = assets.filter((a) => {
    const matchesCat = activeCat === 'all' || a.cat === activeCat;
    const matchesSearch = a.title.toLowerCase().includes(search.toLowerCase()) ||
                          a.prompt.toLowerCase().includes(search.toLowerCase());
    return matchesCat && matchesSearch;
  });

  const handleGenerate = (e) => {
    e.preventDefault();
    if (!prompt.trim()) return;
    setGenerating(true);
    setTimeout(() => {
      const newAsset = {
        id: `a-${Date.now()}`,
        title: prompt.slice(0, 24),
        cat: 'abstract',
        icon: '✨',
        prompt,
        res: '1080x1920'
      };
      setAssets([newAsset, ...assets]);
      setGenerating(false);
      setPrompt('');
    }, 1200);
  };

  return (
    <div className="cg-visuals-page">
      <div className="cg-visuals-header">
        <div>
          <h1 className="cg-heading-lg">🎨 AI Visuals & B-Roll Bin</h1>
          <p className="cg-text-secondary cg-text-sm" style={{ marginTop: 4 }}>
            Local asset library of high-resolution overlays and B-roll cutaways. Zero cloud cost.
          </p>
        </div>
      </div>

      {/* Generator Box */}
      <div className="cg-card cg-visuals-gen-card">
        <h2 className="cg-heading-sm">✨ Generate Contextual Visual</h2>
        <form onSubmit={handleGenerate} className="cg-visuals-gen-form">
          <input
            className="cg-input"
            placeholder="Type a concept (e.g. quantum entanglement glowing particles)..."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={generating}
          />
          <button
            type="submit"
            className="cg-btn cg-btn--primary"
            disabled={!prompt.trim() || generating}
            style={{ minWidth: 140 }}
          >
            {generating ? <><span className="cg-spinner" /> Generating…</> : '✨ Generate Local'}
          </button>
        </form>
      </div>

      {/* Category Filter & Search */}
      <div className="cg-visuals-toolbar">
        <div className="cg-tabs">
          {VISUAL_CATEGORIES.map((cat) => (
            <button
              key={cat.id}
              type="button"
              className={`cg-tab ${activeCat === cat.id ? 'cg-tab--active' : ''}`}
              onClick={() => setActiveCat(cat.id)}
            >
              {cat.label}
            </button>
          ))}
        </div>

        <input
          className="cg-input cg-visuals-search"
          placeholder="Filter assets..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ maxWidth: 220 }}
        />
      </div>

      {/* Visuals Asset Grid */}
      <div className="cg-visuals-grid">
        {filtered.map((item) => (
          <div key={item.id} className="cg-visual-asset-card cg-card">
            <div className="cg-visual-preview-box">
              <span className="cg-visual-big-icon">{item.icon}</span>
              <span className="cg-visual-res-tag">{item.res}</span>
            </div>
            <div className="cg-visual-card-body">
              <h3 className="cg-visual-card-title">{item.title}</h3>
              <p className="cg-text-xs cg-text-muted cg-visual-card-prompt">"{item.prompt}"</p>
              <div className="cg-visual-card-actions">
                <span className="cg-badge cg-badge--muted cg-text-xs">{item.cat}</span>
                <span className="cg-badge cg-badge--success cg-text-xs">Ready</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

