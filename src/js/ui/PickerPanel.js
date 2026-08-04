// Меню выбора: строка серий, под ней сетка панелей. Полка стоит на месте и никуда
// не прыгает, в отличие от эталона, где карточка позиционируется вручную рядом с точкой.

// Плитки проявляются волной. Дальше десятой задержку не растим: хвост длинной
// серии иначе ждал бы своей очереди дольше секунды.
const WAVE_CAP = 10;

export class PickerPanel {
  constructor(root, catalog, model, opts) {
    this.catalog = catalog;
    this.model = model;
    this.opts = opts;
    this.active = model.zones[0];
    this.series = catalog.series[0].id;

    root.innerHTML = '';
    this.zoneRow = el('div', 'viz-zonerow');
    this.seriesRow = el('div', 'viz-series');
    this.grid = el('div', 'viz-grid');
    root.append(this.zoneRow, this.seriesRow, this.grid);

    for (const z of opts.zones) {
      const b = el('button', 'viz-tab');
      b.type = 'button';
      b.textContent = z.title;
      b.dataset.zone = z.id;
      b.addEventListener('click', () => opts.onZone(z.id));
      this.zoneRow.append(b);
    }

    for (const s of catalog.series) {
      const b = el('button', 'viz-tab');
      b.type = 'button';
      b.textContent = s.title;
      b.dataset.series = s.id;
      b.addEventListener('click', () => this.showSeries(s.id));
      this.seriesRow.append(b);
    }

    this.grid.addEventListener('click', (e) => {
      const tile = e.target.closest('.viz-tile');
      if (tile) opts.onPick(this.active, tile.dataset.code);
    });

    model.onChange(() => this.mark());
    this.showSeries(this.series);
  }

  setZone(zone) {
    this.active = zone;
    // Переключились на зону — показываем серию той панели, что в ней сейчас лежит.
    const item = this.opts.item(this.model.get(zone));
    if (item) this.showSeries(item.series);
    else this.mark();
  }

  showSeries(id) {
    this.series = id;
    const s = this.catalog.series.find((x) => x.id === id) || this.catalog.series[0];
    this.grid.innerHTML = '';
    s.items.forEach((it, i) => {
      const t = el('button', 'viz-tile');
      t.type = 'button';
      t.dataset.code = it.code;
      const img = el('img', 'viz-thumb');
      img.loading = 'lazy';
      img.decoding = 'async';
      img.src = this.opts.asset(`tex/${it.code}-t.jpg`);
      img.alt = it.name;
      img.style.setProperty('--i', Math.min(i, WAVE_CAP));
      const cap = el('span', 'viz-cap');
      const nm = el('span', 'viz-name');
      nm.textContent = it.name;
      const art = el('span', 'viz-art');
      // Без артикула позиции в каталоге нет, но напечатать её могут. Так и пишем,
      // иначе под именем висела бы пустая строка и плитки разъезжались бы по высоте.
      art.textContent = it.article || 'под заказ';
      cap.append(nm, art);
      t.append(img, cap);
      this.grid.append(t);
    });
    this.mark();
  }

  mark() {
    const current = this.model.get(this.active);
    this.zoneRow.querySelectorAll('.viz-tab').forEach((b) => {
      b.classList.toggle('is-on', b.dataset.zone === this.active);
    });
    this.seriesRow.querySelectorAll('.viz-tab').forEach((b) => {
      b.classList.toggle('is-on', b.dataset.series === this.series);
    });
    this.grid.querySelectorAll('.viz-tile').forEach((t) => {
      t.classList.toggle('is-on', t.dataset.code === current);
    });
  }
}

function el(tag, cls) { const n = document.createElement(tag); n.className = cls; return n; }
