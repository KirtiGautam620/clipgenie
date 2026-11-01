// Copy text to the clipboard. Some browsers only allow the older way, so try both.
export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch { /* fall through to the older way */ }
  try {
    const area = document.createElement('textarea');
    area.value = text;
    area.style.cssText = 'position:fixed;opacity:0';
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand('copy');
    area.remove();
    return ok;
  } catch {
    return false;
  }
}
