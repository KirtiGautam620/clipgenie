// The Studio timeline shows only what really exists on the clip: its video, the text drawn on it
// (captions, or the user's headline) and the music. Nothing here is invented.

const BREAK_AFTER = '.,?!;:।';
const PAUSE = 0.7;      // same rules the backend uses to group caption words
const HOLD = 0.25;

// ── Time helpers: the finished video is the kept parts of the clip joined together ───────────────
// man.segments are in source seconds; a "finished video" time is counted from 0 over the kept parts.

/** The dissolve length in seconds, or 0 when the clip has no dissolve between its cuts. */
export function dissolveOf(man) {
  return man.transition?.type === 'dissolve' && man.segments.length > 1 ? man.transition.seconds : 0;
}

/** The kept parts added up (what was not cut out), ignoring any dissolve overlap. */
export function keptSeconds(man) {
  return man.segments.reduce((total, s) => total + (s.end - s.start), 0);
}

/** Finished-video time where each kept part starts. A dissolve makes the next part start a little early. */
function partStarts(man) {
  const d = dissolveOf(man);
  const starts = [];
  let t = 0;
  man.segments.forEach((s, i) => {
    starts.push(t);
    t += (s.end - s.start) - (i < man.segments.length - 1 ? d : 0);
  });
  return starts;
}

/** The clip's speed (1 = as recorded). The finished video is the kept parts, sped up by this. */
export function speedOf(man) {
  return man.speed && man.speed > 0 ? man.speed : 1;
}

export function outputLength(man) {
  return (keptSeconds(man) - dissolveOf(man) * Math.max(0, man.segments.length - 1)) / speedOf(man);
}

export function isCut(man) {
  return Math.abs(outputLength(man) - (man.clip.end - man.clip.start)) > 0.01;
}

/** A source time -> finished-video time, or null when that moment was cut out. */
export function sourceToOut(man, abs) {
  const starts = partStarts(man);
  for (let i = 0; i < man.segments.length; i++) {
    const s = man.segments[i];
    if (abs >= s.start - 0.001 && abs <= s.end + 0.001) return (starts[i] + Math.max(0, abs - s.start)) / speedOf(man);
  }
  return null;
}

/** A finished-video time -> source time. */
export function outToSource(man, t) {
  const starts = partStarts(man);
  const u = t * speedOf(man);                // finished-video seconds -> seconds in the kept parts
  for (let i = 0; i < man.segments.length; i++) {
    const s = man.segments[i];
    const nextStart = i < man.segments.length - 1 ? starts[i + 1] : Infinity;
    if (u < nextStart - 1e-9 || i === man.segments.length - 1) return s.start + Math.max(0, u - starts[i]);
  }
  return man.segments[man.segments.length - 1].end;
}

/**
 * Remove the finished-video range [fromOut, toOut] from the kept parts. Returns the new list of parts
 * in source seconds. The range is read against `man`'s current parts, so cuts can be stacked.
 */
export function cutSegments(man, fromOut, toOut) {
  const a = outToSource(man, fromOut);
  const b = outToSource(man, toOut);
  const next = [];
  for (const s of man.segments) {
    if (b <= s.start || a >= s.end) { next.push({ start: s.start, end: s.end }); continue; }
    if (a > s.start) next.push({ start: s.start, end: a });
    if (b < s.end) next.push({ start: b, end: s.end });
  }
  return next
    .filter((s) => s.end - s.start > 0.05)
    .map((s) => ({ start: Math.round(s.start * 1000) / 1000, end: Math.round(s.end * 1000) / 1000 }));
}

/**
 * The removed stretches between the kept parts, in source seconds. Each one can be put back.
 * Returns [{ index, start, end, length }] where index is the part before the gap.
 */
export function removedGaps(parts) {
  const gaps = [];
  for (let i = 0; i < parts.length - 1; i++) {
    const start = parts[i].end;
    const end = parts[i + 1].start;
    // only a part that comes later in the clip, after this one, leaves a gap; a moved part does not
    if (end - start > 0.05) gaps.push({ index: i, start, end, length: Math.round((end - start) * 100) / 100 });
  }
  return gaps;
}

/** Move a kept part one place earlier (dir = -1) or later (dir = 1) in the play order. */
export function movePart(parts, index, dir) {
  const to = index + dir;
  if (index < 0 || to < 0 || index >= parts.length || to >= parts.length) return parts.map((s) => ({ ...s }));
  const next = parts.map((s) => ({ ...s }));
  [next[index], next[to]] = [next[to], next[index]];
  return next;
}

/** Put one removed stretch back: the parts on either side of it join into one. */
export function restoreGap(parts, index) {
  if (index < 0 || index >= parts.length - 1) return parts.map((s) => ({ ...s }));
  if (parts[index + 1].start < parts[index].end) return parts.map((s) => ({ ...s }));   // moved parts: nothing to join
  const joined = { start: parts[index].start, end: parts[index + 1].end };
  return [...parts.slice(0, index).map((s) => ({ ...s })), joined, ...parts.slice(index + 2).map((s) => ({ ...s }))];
}

/** Caption words (stored from the clip's start) in finished-video time; words that were cut are dropped. */
// Each word keeps `idx`, its place in the clip's saved caption words, so an edit can find it again.
export function mapWords(words, man) {
  if (!man || !isCut(man)) return words.map((w, idx) => ({ ...w, idx }));
  const out = [];
  words.forEach((w, idx) => {
    const start = sourceToOut(man, man.clip.start + w.start);
    const end = sourceToOut(man, man.clip.start + w.end);
    if (start !== null && end !== null && end >= start) out.push({ ...w, start, end, idx });
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
    return { id: `cap-${i}`, title: g.map((w) => w.text).join(' '), start, duration: Math.max(0.2, end - start),
      wordIdx: g.map((w) => w.idx), editable: true };
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
      blocks: [{ id: 'hook', title: hook.text, start: 0, duration: Math.min(seconds, duration), resizable: true }] });
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
