// Точка входа: грузим конфиги, собираем модель, поднимаем сцену и меню.
import { validateCatalog, findItem } from './core/CatalogLoader.js?v=20260804c';
import { SceneModel } from './core/SceneModel.js?v=20260804c';
import { encodeState, decodeState } from './core/ShareState.js?v=20260804c';
import { Scene } from './ui/Scene.js?v=20260804c';
import { PickerPanel } from './ui/PickerPanel.js?v=20260804c';
import { saveImage } from './ui/SaveImage.js?v=20260804c';

const V = '20260804c';
const asset = (p) => `assets/${p}?v=${V}`;
const shell = document.querySelector('.viz');

// Прятать содержимое имеет право только живой скрипт: иначе упавший модуль
// оставил бы пустую страницу вместо хотя бы статичной сцены.
shell.classList.add('is-anim');
const reveal = () => shell.classList.add('is-ready');

async function json(path) {
  const r = await fetch(`${path}?v=${V}`);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

// Событие уходит наружу: на боевой странице его подхватит Метрика.
function track(event, payload) {
  try {
    if (typeof window.ym === 'function' && window.VIZ_METRIKA_ID) {
      window.ym(window.VIZ_METRIKA_ID, 'reachGoal', event, payload);
    }
    window.parent.postMessage({ type: 'viz', event, payload }, '*');
  } catch { /* аналитика не должна ломать страницу */ }
}

// Высота страницы уходит наверх сообщением: встроенный iframe своей высоты не знает,
// а событие resize ВНУТРИ iframe не приходит вовсе. Поэтому следим за самим документом.
function postSize() {
  try {
    const h = Math.ceil(document.documentElement.getBoundingClientRect().height);
    window.parent.postMessage({ type: 'viz-size', height: h }, '*');
  } catch { /* сообщение наверх не должно ломать страницу */ }
}

async function boot() {
  const [scene, rawCatalog, fg] = await Promise.all([
    json('src/config/scene.json'),
    json('src/config/catalog.json'),
    json('assets/scene/fg.json'),
  ]);
  const catalog = validateCatalog(rawCatalog);
  const model = new SceneModel(scene);
  const item = (code) => findItem(catalog, code);

  const restored = decodeState(location.hash, model.zones, (c) => !!item(c));
  for (const [z, c] of Object.entries(restored)) model.state[z] = c;

  const opts = { asset, item, zones: scene.zones };
  const view = new Scene(document.getElementById('viz-scene'), scene, fg, model, opts);
  const picker = new PickerPanel(document.getElementById('viz-picker'), catalog, model, {
    ...opts,
    onZone: (z) => { view.setActive(z); picker.setZone(z); },
    onPick: (z, code) => {
      if (!model.set(z, code)) return;
      const it = item(code);
      track('viz_pick', { zone: z, series: it.series, article: code });
    },
  });

  document.getElementById('viz-scene').addEventListener('click', (e) => {
    const box = e.target.closest('.viz-zone');
    if (!box) return;
    view.setActive(box.dataset.zone);
    picker.setZone(box.dataset.zone);
  });

  model.onChange(() => {
    location.replace(`#${encodeState(model.state, model.zones)}`);
    document.getElementById('viz-reset').disabled = model.isDefault();
    const cur = item(model.get(picker.active));
    const link = document.getElementById('viz-product');
    // Кнопка перехода к товару появляется сама, когда в таблице каталога заполнят адрес.
    if (cur && cur.url) { link.href = cur.url; link.hidden = false; }
    else link.hidden = true;
  });

  document.getElementById('viz-reset').addEventListener('click', () => {
    model.reset();
    track('viz_reset', {});
  });
  document.getElementById('viz-save').addEventListener('click', async (e) => {
    e.target.disabled = true;
    try { await saveImage(scene, fg, model, opts); track('viz_save', { ...model.state }); }
    finally { e.target.disabled = false; }
  });
  document.getElementById('viz-product').addEventListener('click', () => {
    track('viz_to_product', { article: model.get(picker.active) });
  });

  document.getElementById('viz-note').textContent = scene.disclaimer;
  view.setActive(model.zones[0]);
  picker.setZone(model.zones[0]);
  document.getElementById('viz-reset').disabled = model.isDefault();
  reveal();
  postSize();
  new ResizeObserver(postSize).observe(document.documentElement);
  track('viz_open', {});
}

boot().catch((err) => {
  document.getElementById('viz-error').textContent = `Не удалось загрузить визуализатор: ${err.message}`;
  document.getElementById('viz-error').hidden = false;
  reveal();
});
