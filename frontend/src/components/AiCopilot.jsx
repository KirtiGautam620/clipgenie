import React, { useState } from 'react';
import './AiCopilot.css';

const SUGGESTED_PROMPTS = [
  "Make this video more cinematic",
  "Add punch-in zooms on punchlines",
  "Generate visuals related to speech topic",
  "Make captions more attractive",
  "Add subtle lo-fi background music",
  "Make first 3 seconds more engaging",
];

export default function AiCopilot({ onApplyPromptAction, onUndoAction, canUndo }) {
  const [prompt, setPrompt] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [pendingDiff, setPendingDiff] = useState(null);

  const handleRunPrompt = (textToRun) => {
    const query = textToRun || prompt;
    if (!query.trim()) return;
    setIsProcessing(true);

    setTimeout(() => {
      let diff = {
        query,
        changes: [],
        actionData: {},
      };

      if (query.toLowerCase().includes('cinematic') || query.toLowerCase().includes('color')) {
        diff.changes = [
          'Applied Cinematic Teal & Orange color grade',
          'Added subtle 15px depth-of-field background blur',
          'Set background music volume to 35% with speech ducking'
        ];
        diff.actionData = { type: 'cinematic', filter: 'contrast(125%) saturate(115%) hue-rotate(-10deg)', volume: 0.35 };
      } else if (query.toLowerCase().includes('zoom') || query.toLowerCase().includes('engaging') || query.toLowerCase().includes('first 3')) {
        diff.changes = [
          'Added 1.25x punch-in zoom effect at 00:01.50 - 00:04.00',
          'Inserted dynamic camera shake at the opening hook',
          'Boosted caption size to emphasize the first sentence'
        ];
        diff.actionData = { type: 'zoom_punch', zoom: 1.25 };
      } else if (query.toLowerCase().includes('visual') || query.toLowerCase().includes('b-roll')) {
        diff.changes = [
          'Extracted speech concept: "Neural intelligence"',
          'Added PiP AI B-Roll visual block at 00:03.00 - 00:07.00',
        ];
        diff.actionData = { type: 'broll_insert' };
      } else if (query.toLowerCase().includes('caption')) {
        diff.changes = [
          'Switched caption theme to Viral Highlighter',
          'Set active word highlight color to Electric Yellow',
          'Aligned to 70% vertical safe zone'
        ];
        diff.actionData = { type: 'caption_theme', theme: 'viral', color: '#FFD400' };
      } else {
        diff.changes = [
          'Analyzed speech cadence and optimized cut pacing',
          'Added smooth audio crossfade to smooth speech transitions',
          'Applied subtle audio normalization'
        ];
        diff.actionData = { type: 'general' };
      }

      setPendingDiff(diff);
      setIsProcessing(false);
      setPrompt('');
    }, 1100);
  };

  const handleApply = () => {
    if (!pendingDiff) return;
    onApplyPromptAction(pendingDiff.actionData);
    setPendingDiff(null);
  };

  const handleDiscard = () => {
    setPendingDiff(null);
  };

  return (
    <div className="cg-copilot-card">
      <div className="cg-copilot-header">
        <div className="cg-copilot-title-group">
          <span className="cg-copilot-sparkle">⚡</span>
          <div>
            <h3 className="cg-copilot-title">AI Editing Assistant</h3>
            <span className="cg-text-xs cg-text-muted">Powered by Local Ollama Copilot</span>
          </div>
        </div>
        {canUndo && (
          <button
            type="button"
            className="cg-btn cg-btn--sm cg-btn--ghost"
            onClick={onUndoAction}
            title="Undo Last Action (⌘Z)"
          >
            ↩ Undo
          </button>
        )}
      </div>

      {/* Suggested Prompt Chips */}
      <div className="cg-copilot-chips">
        {SUGGESTED_PROMPTS.map((sp) => (
          <button
            key={sp}
            type="button"
            className="cg-copilot-chip"
            onClick={() => handleRunPrompt(sp)}
            disabled={isProcessing}
          >
            {sp}
          </button>
        ))}
      </div>

      {/* Input Row */}
      <form
        onSubmit={(e) => { e.preventDefault(); handleRunPrompt(); }}
        className="cg-copilot-input-box"
      >
        <input
          className="cg-input cg-copilot-input"
          placeholder="Ask AI Copilot to polish or re-time..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          disabled={isProcessing}
        />
        <button
          type="submit"
          className="cg-btn cg-btn--primary cg-btn--sm"
          disabled={!prompt.trim() || isProcessing}
        >
          {isProcessing ? <span className="cg-spinner" /> : 'Run'}
        </button>
      </form>

      {/* Pending Diff Banner */}
      {pendingDiff && (
        <div className="cg-copilot-diff-banner">
          <div className="cg-diff-header">
            <span className="cg-badge cg-badge--accent">Proposed Edits</span>
            <span className="cg-text-xs cg-text-muted">"{pendingDiff.query}"</span>
          </div>
          <ul className="cg-diff-list">
            {pendingDiff.changes.map((ch, idx) => (
              <li key={idx} className="cg-diff-item">
                <span className="cg-diff-check">✓</span>
                <span>{ch}</span>
              </li>
            ))}
          </ul>
          <div className="cg-diff-actions">
            <button
              type="button"
              className="cg-btn cg-btn--sm cg-btn--secondary"
              onClick={handleDiscard}
            >
              Discard
            </button>
            <button
              type="button"
              className="cg-btn cg-btn--sm cg-btn--primary"
              onClick={handleApply}
            >
              ✨ Apply Edits
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

