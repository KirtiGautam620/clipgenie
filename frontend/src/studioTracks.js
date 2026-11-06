// The Studio timeline shows only what really exists on the clip: its video, the text drawn on it
// (captions, or the user's headline) and the music. Nothing here is invented.

const BREAK_AFTER = '.,?!;:।';
const PAUSE = 0.7;      // same rules the backend uses to group caption words
const HOLD = 0.25;

// ── Time helpers: the finished video is the kept parts of the clip joined together ───────────────
// man.segments are in source seconds; a "finished video" time is counted from 0 over the kept parts.

export function outputLength(man) {
  return man.segments.reduce((total, s) => total + (s.end - s.start), 0);
}

export function isCut(man) {
  return Math.abs(outputLength(man) - (man.clip.end - man.clip.start)) > 0.01;
}

/** A source time -> finished-video time, or null when that moment was cut out. */
export function sourceToOut(man, abs) {
  let done = 0;
  for (const s of man.segments) {
    if (abs >= s.start - 0.001 && abs <= s.end + 0.001) return done + Math.max(0, abs - s.start);
    done += s.end - s.start;
  }
  return null;
}

/** A finished-video time -> source time. */
export function outToSource(man, t) {
  let done = 0;
  for (const s of man.segments) {
    const len = s.end - s.start;
    if (t <= done + len + 1e-9) return s.start + Math.max(0, t - done);
    done += len;
  }
  return man.segments[man.segments.length - 1].end;
}

/** Caption words (stored from the clip's start) in finished-video time; words that were cut are dropped. */
export function mapWords(words, man) {
  if (!man || !isCut(man)) return words;
  const out = [];
  words.forEach((w) => {
    const start = sourceToOut(man, man.clip.start + w.start);
    const end = sourceToOut(man, man.clip.start + w.end);
    if (start !== null && end !== null && end >= start) out.push({ ...w, start, end });
  });
  return out;
}

export function captionBlocks(captions, man) {
  const words = mapWords(captions?.words || [], man);
  if (!words.length) return [];
  const max = captions.style?.words_per_line || 4;
  const groups = [];
  let cur = [];
  words.forEach((w) => {
    if (cur.length && (cur.length >= max || w.start - cur[cur.length - 1].end > PAUSE)) {
      groups.push(cur);
      cur = [];
    }
    cur.push(w);
    if (BREAK_AFTER.includes(w.text.slice(-1))) {
      groups.push(cur);
      cur = [];
    }
  });
  if (cur.length) groups.push(cur);
  return groups.map((g, i) => {
    const start = g[0].start;
    const nextStart = groups[i + 1]?.[0].start ?? Infinity;
    const end = Math.min(g[g.length - 1].end + HOLD, nextStart);
    return { id: `cap-${i}`, title: g.map((w) => w.text).join(' '), start, duration: Math.max(0.2, end - start) };
  });
}

export function buildTracks(clip, duration, man) {
  const text = clip.text || {};
  let textBlocks = [];
  let textLabel = 'Text';
  if (text.mode === 'headline' && text.headline?.text) {
    const seconds = text.headline.style?.seconds;
    textLabel = 'Headline';
    textBlocks = [{ id: 'headline', title: text.headline.text, start: 0,
      duration: seconds ? Math.min(seconds, duration) : duration }];
  } else if (text.mode === 'captions' || !clip.text) {
    textLabel = 'Captions';
    textBlocks = captionBlocks(clip.captions, man);
  }
  const tracks = [
    { key: 'video', label: 'Video', blocks: videoBlocks(clip, duration, man) },
    { key: 'captions', label: textLabel, blocks: textBlocks },
  ];
  const hook = text.hook;
  if (hook?.approved && (text.mode === 'captions' || text.mode === 'none')) {
    const seconds = hook.style?.seconds || duration;
    tracks.push({ key: 'effects', label: 'Hook',
      blocks: [{ id: 'hook', title: hook.text, start: 0, duration: Math.min(seconds, duration) }] });
  }
  tracks.push({ key: 'music', label: 'Music', blocks: clip.music
    ? [{ id: 'music', title: `${clip.music.title} (${Math.round((clip.music.volume ?? 0.6) * 100)}%)`, start: 0, duration }]
    : [] });
  return tracks;
}

// One block per kept part, so shortened pauses show up as the joins between blocks.
function videoBlocks(clip, duration, man) {
  const title = clip.title || `Clip ${clip.id}`;
  if (!man || !isCut(man)) return [{ id: 'video', title, start: 0, duration }];
  let done = 0;
  return man.segments.map((s, i) => {
    const block = { id: `video-${i}`, title: i === 0 ? title : '', start: done, duration: s.end - s.start };
    done += s.end - s.start;
    return block;
  });
}

export const FRAMING_LABELS = {
  track: "Follows the speaker's face",
  static: "Framed on the speaker's face",
  center: 'Centre crop',
  blur: 'Whole picture on a blurred background',
};
