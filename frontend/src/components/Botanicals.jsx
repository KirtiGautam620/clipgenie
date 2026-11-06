// Original CocoGenie botanical artwork: a logo mark and a few leaf sprigs.
// Drawn here as plain SVG (no image files, no packages). They use the colour tokens, so they follow
// the theme. They are decoration only, so every one is hidden from screen readers.

const LEAF = 'M0 0 C 9 -9 24 -9 34 0 C 24 9 9 9 0 0 Z';

/** The CocoGenie mark: a leaf with a play triangle in it. */
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

/**
 * Friendly panda in several poses. Decoration only; hidden from screen readers.
 * pose: 'happy' (default) | 'sleeping' | 'singing' | 'working' | 'worried' | 'waving'
 */
export function Panda({ width = 96, className = '', pose = 'happy' }) {
  const ink = 'var(--cg-text-primary)';
  const closedEyes = pose === 'sleeping' || pose === 'singing';

  return (
    <svg className={className} width={width} viewBox="0 0 120 120" aria-hidden="true" focusable="false">
      {/* ears + head */}
      <circle cx="28" cy="30" r="13" fill={ink} />
      <circle cx="92" cy="30" r="13" fill={ink} />
      <ellipse cx="60" cy="64" rx="44" ry="38" fill="#FFFFFF" stroke="var(--cg-border-default)" strokeWidth="1.5" />

      {/* eyes */}
      {closedEyes ? (
        <>
          <path d="M33 60 Q41 68 49 60" stroke={ink} strokeWidth="2.6" fill="none" strokeLinecap="round" />
          <path d="M71 60 Q79 68 87 60" stroke={ink} strokeWidth="2.6" fill="none" strokeLinecap="round" />
        </>
      ) : (
        <>
          <ellipse cx="41" cy="58" rx="11" ry="14" transform="rotate(-20 41 58)" fill={ink} />
          <ellipse cx="79" cy="58" rx="11" ry="14" transform="rotate(20 79 58)" fill={ink} />
          <circle cx="44" cy="55" r="3.2" fill="#FFFFFF" />
          <circle cx="76" cy="55" r="3.2" fill="#FFFFFF" />
        </>
      )}
      {pose === 'worried' && (
        <>
          <path d="M31 40 L45 46" stroke={ink} strokeWidth="2" strokeLinecap="round" />
          <path d="M89 40 L75 46" stroke={ink} strokeWidth="2" strokeLinecap="round" />
        </>
      )}

      {/* cheeks + nose */}
      <ellipse cx="31" cy="76" rx="6" ry="4" fill="var(--cg-blush)" />
      <ellipse cx="89" cy="76" rx="6" ry="4" fill="var(--cg-blush)" />
      <ellipse cx="60" cy="72" rx="4.5" ry="3.2" fill={ink} />

      {/* mouth */}
      {pose === 'singing' ? (
        <ellipse cx="60" cy="84" rx="5" ry="6" fill={ink} />
      ) : pose === 'worried' ? (
        <path d="M52 86 Q56 82 60 86 Q64 90 68 86" stroke={ink} strokeWidth="1.8" fill="none" strokeLinecap="round" />
      ) : pose === 'sleeping' ? (
        <path d="M56 82 Q60 84 64 82" stroke={ink} strokeWidth="1.8" fill="none" strokeLinecap="round" />
      ) : (
        <path d="M54 80 Q60 85 66 80" stroke={ink} strokeWidth="1.8" fill="none" strokeLinecap="round" />
      )}

      {/* pose extras */}
      {pose === 'sleeping' && (
        <g fill={ink} opacity="0.6" style={{ fontFamily: 'var(--cg-font-display)', fontWeight: 700 }}>
          <text x="88" y="26" fontSize="11">z</text>
          <text x="98" y="14" fontSize="14">Z</text>
        </g>
      )}
      {pose === 'singing' && (
        <g fill="var(--cg-forest)">
          <circle cx="104" cy="40" r="3.2" />
          <path d="M107 40 L107 22 Q112 26 114 32" stroke="var(--cg-forest)" strokeWidth="1.6" fill="none" />
          <circle cx="16" cy="48" r="2.6" />
          <path d="M18.6 48 L18.6 34" stroke="var(--cg-forest)" strokeWidth="1.4" fill="none" />
        </g>
      )}
      {pose === 'working' && (
        <g fill="var(--cg-peach-ink)">
          <path d="M104 22 L105.3 25.7 L109 27 L105.3 28.3 L104 32 L102.7 28.3 L99 27 L102.7 25.7 Z" />
          <path d="M18 30 L18.9 32.6 L21.5 33.5 L18.9 34.4 L18 37 L17.1 34.4 L14.5 33.5 L17.1 32.6 Z" opacity="0.8" />
        </g>
      )}
      {pose === 'worried' && (
        <path d="M90 42 Q94 48 94 51 A4 4 0 0 1 86 51 Q86 48 90 42 Z" fill="var(--cg-info)" />
      )}
      {pose === 'waving' && (
        <>
          <ellipse cx="104" cy="62" rx="9" ry="11" fill="#FFFFFF" stroke="var(--cg-border-default)" strokeWidth="1.5" />
          <path d="M113 46 Q118 50 113 54" stroke={ink} strokeWidth="1.6" fill="none" strokeLinecap="round" />
          <path d="M117 42 Q124 50 117 58" stroke={ink} strokeWidth="1.4" fill="none" strokeLinecap="round" opacity="0.6" />
        </>
      )}

      {/* bamboo leaf */}
      <path d={LEAF} transform="translate(86 100) rotate(-40) scale(0.7)" fill="var(--cg-sage)" />
    </svg>
  );
}
