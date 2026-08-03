// Выбор пишется в адрес страницы, чтобы комбинацию можно было переслать ссылкой.

export function encodeState(state, zones) {
  return zones.map((z) => `${z}=${encodeURIComponent(state[z])}`).join('&');
}

export function decodeState(hash, zones, valid) {
  const out = {};
  const raw = String(hash || '').replace(/^#/, '');
  if (!raw) return out;
  for (const part of raw.split('&')) {
    const i = part.indexOf('=');
    if (i < 1) continue;
    const key = part.slice(0, i);
    let val;
    try { val = decodeURIComponent(part.slice(i + 1)); } catch { continue; }
    // Мусор в адресе не должен ронять страницу: неизвестное просто пропускаем.
    if (zones.includes(key) && valid(val)) out[key] = val;
  }
  return out;
}
