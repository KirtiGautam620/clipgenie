// Small helper: call the backend and turn errors into readable messages.
export async function getJSON(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = Array.isArray(body.detail) ? "Invalid value" : body.detail;
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res.json();
}
