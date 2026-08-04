import test from 'node:test';
import assert from 'node:assert/strict';
import { validateCatalog, findItem } from '../src/js/core/CatalogLoader.js';
import { SceneModel } from '../src/js/core/SceneModel.js';
import { readFileSync } from 'node:fs';
import { encodeState, decodeState } from '../src/js/core/ShareState.js';

const catalog = validateCatalog({
  series: [
    { id: 'wood', title: 'Дерево', items: [{ code: 'W1', label: 'W1' }, { code: 'W2', label: 'W2', url: 'https://x/1' }] },
    { id: 'stone', title: 'Камень', items: [{ code: 'S1', label: 'S1' }] },
  ],
});
const scene = {
  zones: [{ id: 'left' }, { id: 'center' }, { id: 'right' }],
  defaults: { left: 'W1', center: 'W1', right: 'W1' },
};

test('каталог: пустая ссылка не ломает разбор', () => {
  assert.equal(findItem(catalog, 'W1').url, '');
  assert.equal(findItem(catalog, 'W2').url, 'https://x/1');
});

test('каталог: дубль артикула отвергается', () => {
  assert.throws(() => validateCatalog({
    series: [{ id: 'a', title: 'A', items: [{ code: 'X' }, { code: 'X' }] }],
  }), /дважды/);
});

test('каталог: серия без панелей отвергается', () => {
  assert.throws(() => validateCatalog({ series: [{ id: 'a', title: 'A', items: [] }] }), /без панелей/);
});

test('модель: стартовое состояние одинаковое во всех трёх зонах', () => {
  const m = new SceneModel(scene);
  assert.deepEqual(m.state, { left: 'W1', center: 'W1', right: 'W1' });
  assert.equal(m.isDefault(), true);
});

test('модель: сброс возвращает стартовое состояние, а не пустую стену', () => {
  const m = new SceneModel(scene);
  m.set('center', 'S1');
  assert.equal(m.isDefault(), false);
  m.reset();
  assert.deepEqual(m.state, scene.defaults);
  assert.equal(m.isDefault(), true);
});

test('модель: повторная установка того же значения не считается изменением', () => {
  const m = new SceneModel(scene);
  assert.equal(m.set('left', 'S1'), true);
  assert.equal(m.set('left', 'S1'), false);
});

test('модель: неизвестная зона игнорируется', () => {
  const m = new SceneModel(scene);
  assert.equal(m.set('ceiling', 'S1'), false);
});

test('адрес: состояние кодируется и восстанавливается', () => {
  const zones = ['left', 'center', 'right'];
  const st = { left: 'W1', center: 'S1', right: 'W2' };
  const back = decodeState('#' + encodeState(st, zones), zones, () => true);
  assert.deepEqual(back, st);
});

test('адрес: мусор не роняет разбор', () => {
  const zones = ['left', 'center', 'right'];
  assert.deepEqual(decodeState('#левая&&=&right=W1&ceiling=Z', zones, (c) => c === 'W1'), { right: 'W1' });
  assert.deepEqual(decodeState('', zones, () => true), {});
  assert.deepEqual(decodeState('#left=%E0%A4%A', zones, () => true), {});
});

test('адрес: неизвестный артикул отбрасывается', () => {
  const zones = ['left'];
  assert.deepEqual(decodeState('#left=NOPE', zones, (c) => !!findItem(catalog, c)), {});
});

// Клиент просил равные зоны. Проверка держит это требование: рамки на рендере
// подвинуты вручную, и случайная правка конфига легко разъехалась бы с картинкой.
test('сцена: три зоны равны по ширине и не перекрываются', () => {
  const cfg = JSON.parse(readFileSync(new URL('../src/config/scene.json', import.meta.url), 'utf8'));
  const px = cfg.zones.map((z) => ({
    id: z.id,
    x0: z.rect[0] * cfg.width,
    w: z.rect[2] * cfg.width,
  }));
  assert.equal(px.length, 3);
  for (const z of px) assert.ok(Math.abs(z.w - px[0].w) < 0.5, `ширина зоны ${z.id}: ${z.w}`);
  const sorted = [...px].sort((a, b) => a.x0 - b.x0);
  for (let i = 1; i < sorted.length; i++) {
    assert.ok(sorted[i].x0 >= sorted[i - 1].x0 + sorted[i - 1].w, `зоны ${sorted[i - 1].id} и ${sorted[i].id} налезают`);
  }
});

test('сцена: высота зон одинаковая', () => {
  const cfg = JSON.parse(readFileSync(new URL('../src/config/scene.json', import.meta.url), 'utf8'));
  const [first] = cfg.zones;
  for (const z of cfg.zones) {
    assert.equal(z.rect[1], first.rect[1], `верх зоны ${z.id}`);
    assert.equal(z.rect[3], first.rect[3], `высота зоны ${z.id}`);
  }
});
