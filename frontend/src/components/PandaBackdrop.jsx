import { Panda } from './Botanicals.jsx';

// Decorative panda pattern behind the app's content. Original drawings (see Botanicals.jsx),
// scattered loosely and kept faint so cards and text stay easy to read. Hidden from screen readers.
const PANDAS = [
  { x: 4,  y: 5,  w: 84, r: -12, pose: 'happy' },
  { x: 30, y: 3,  w: 64, r: 8,   pose: 'sleeping' },
  { x: 72, y: 4,  w: 80, r: 0,   pose: 'waving' },
  { x: 10, y: 30, w: 72, r: 6,   pose: 'singing' },
  { x: 56, y: 27, w: 60, r: -6,  pose: 'working' },
  { x: 86, y: 36, w: 70, r: 10,  pose: 'happy' },
  { x: 3,  y: 58, w: 66, r: -8,  pose: 'worried' },
  { x: 38, y: 60, w: 88, r: 4,   pose: 'sleeping' },
  { x: 70, y: 63, w: 74, r: -4,  pose: 'waving' },
  { x: 18, y: 86, w: 80, r: 12,  pose: 'happy' },
  { x: 60, y: 88, w: 66, r: -10, pose: 'singing' },
  { x: 88, y: 92, w: 60, r: 6,   pose: 'working' },
];

const HEARTS = [
  { x: 24, y: 18, s: 14 }, { x: 64, y: 14, s: 11 }, { x: 46, y: 46, s: 13 },
  { x: 92, y: 20, s: 12 }, { x: 8, y: 74, s: 11 },  { x: 52, y: 78, s: 14 },
];

export default function PandaBackdrop() {
  return (
    <div className="cg-panda-backdrop" aria-hidden="true">
      {PANDAS.map((p, i) => (
        <span key={`p${i}`} className="cg-panda-spot"
          style={{ left: `${p.x}%`, top: `${p.y}%`, transform: `rotate(${p.r}deg)` }}>
          <Panda width={p.w} pose={p.pose} />
        </span>
      ))}
      {HEARTS.map((h, i) => (
        <span key={`h${i}`} className="cg-panda-heart" style={{ left: `${h.x}%`, top: `${h.y}%`, fontSize: h.s }}>♥</span>
      ))}
    </div>
  );
}
