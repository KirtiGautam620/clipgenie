// Original ClipGenie botanical artwork: a logo mark and a few leaf sprigs.
// Drawn here as plain SVG (no image files, no packages). They use the colour tokens, so they follow
// the theme. They are decoration only, so every one is hidden from screen readers.

const LEAF = 'M0 0 C 9 -9 24 -9 34 0 C 24 9 9 9 0 0 Z';

/** The ClipGenie mark: a leaf with a play triangle in it. */
export function LogoMark({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <path d="M16 2.5 C25 5.5 29.5 13 27 21.5 C25 27.5 19 29.5 16 29.5 C13 29.5 7 27.5 5 21.5 C2.5 13 7 5.5 16 2.5 Z"
        fill="var(--cg-forest)" />
      <path d="M16 29.5 C16 22 16 14 16 8" stroke="var(--cg-leaf)" strokeWidth="1" fill="none"
        strokeLinecap="round" opacity="0.55" />
      <path d="M13 11.5 L21.5 16.5 L13 21.5 Z" fill="var(--cg-ivory)" />
    </svg>
  );
}

/** A curved branch with alternating leaves. `flip` mirrors it so two can frame a screen. */
export function Sprig({ width = 120, flip = false, className = '', tone = 'sage' }) {
  const fillA = tone === 'leaf' ? 'var(--cg-leaf)' : 'var(--cg-sage)';
  const fillB = tone === 'leaf' ? 'var(--cg-mint)' : 'var(--cg-leaf)';
  // [x, y, rotation in degrees, scale, which fill]
  const leaves = [
    [58, 168, -150, 0.9, 0], [64, 150, -35, 0.95, 1],
    [70, 126, -155, 0.9, 1], [78, 106, -30, 0.95, 0],
    [84, 82, -160, 0.85, 0], [92, 62, -28, 0.85, 1],
    [98, 40, -150, 0.75, 1], [104, 22, -60, 0.8, 0],
  ];
  return (
    <svg className={className} width={width} viewBox="0 0 140 200" aria-hidden="true" focusable="false"
      style={flip ? { transform: 'scaleX(-1)' } : undefined}>
      <path d="M50 198 C 56 160 70 110 108 12" stroke="var(--cg-forest)" strokeWidth="2" fill="none"
        strokeLinecap="round" opacity="0.7" />
      {leaves.map(([x, y, rot, scale, f], i) => (
        <path key={i} d={LEAF} transform={`translate(${x} ${y}) rotate(${rot}) scale(${scale})`}
          fill={f === 0 ? fillA : fillB} opacity="0.85" />
      ))}
    </svg>
  );
}

/** Three small leaves: a quiet divider or empty-state accent. */
export function LeafTrio({ size = 56 }) {
  return (
    <svg width={size} height={size * 0.6} viewBox="0 0 60 36" aria-hidden="true" focusable="false">
      <path d={LEAF} transform="translate(8 26) rotate(-48) scale(0.8)" fill="var(--cg-sage)" opacity="0.9" />
      <path d={LEAF} transform="translate(26 30) rotate(-90) scale(0.95)" fill="var(--cg-forest)" opacity="0.9" />
      <path d={LEAF} transform="translate(44 26) rotate(-132) scale(0.8)" fill="var(--cg-leaf)" />
    </svg>
  );
}
