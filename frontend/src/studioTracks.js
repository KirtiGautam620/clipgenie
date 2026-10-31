// The Studio timeline shows only what really exists on the clip: its video, the text drawn on it
// (captions, or the user's headline) and the music. Nothing here is invented.

const BREAK_AFTER = '.,?!;:।';
const PAUSE = 0.7;      // same rules the backend uses to group caption words
const HOLD = 0.25;

export function captionBlocks(captions) {
  const words = captions?.words || [];
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

export function buildTracks(clip, duration) {
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
    textBlocks = captionBlocks(clip.captions);
  }
  return [
    { key: 'video', label: 'Video', blocks: [{ id: 'video', title: clip.title || `Clip ${clip.id}`, start: 0, duration }] },
    { key: 'captions', label: textLabel, blocks: textBlocks },
    { key: 'music', label: 'Music', blocks: clip.music
      ? [{ id: 'music', title: `${clip.music.title} (${Math.round((clip.music.volume ?? 0.6) * 100)}%)`, start: 0, duration }]
      : [] },
  ];
}

export const FRAMING_LABELS = {
  track: "Follows the speaker's face",
  static: "Framed on the speaker's face",
  center: 'Centre crop',
  blur: 'Whole picture on a blurred background',
};
