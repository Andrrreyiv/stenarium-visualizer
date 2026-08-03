// Сцена: фон, три зоны с текстурой, множительный слой света, передний слой с диваном.
// Всё в долях от кадра, поэтому пересчёт при изменении размера окна не нужен вовсе.

export class Scene {
  constructor(root, scene, fg, model, opts) {
    this.scene = scene;
    this.model = model;
    this.opts = opts;
    this.tiles = {};

    root.style.aspectRatio = `${scene.width} / ${scene.height}`;
    root.innerHTML = '';

    const bg = el('img', 'viz-bg');
    bg.src = opts.asset('scene/bg.jpg');
    bg.alt = 'Интерьер';
    bg.decoding = 'async';
    root.append(bg);

    for (const z of scene.zones) {
      const box = el('button', 'viz-zone');
      box.type = 'button';
      box.dataset.zone = z.id;
      box.setAttribute('aria-label', `${z.title} стена`);
      place(box, z.rect);
      const fill = el('span', 'viz-fill');
      box.append(fill);
      root.append(box);
      this.tiles[z.id] = fill;
    }

    const shade = el('img', 'viz-shade');
    shade.src = opts.asset('scene/shade.png');
    shade.alt = '';
    shade.setAttribute('aria-hidden', 'true');
    root.append(shade);

    const front = el('img', 'viz-fg');
    front.src = opts.asset('scene/fg.png');
    front.alt = '';
    front.setAttribute('aria-hidden', 'true');
    place(front, fg.rect);
    root.append(front);

    this.root = root;
    model.onChange(() => this.render());
    this.render();
  }

  render() {
    for (const z of this.scene.zones) {
      const code = this.model.get(z.id);
      const item = this.opts.item(code);
      if (!item) continue;
      const across = this.scene.tilesAcross[item.series] || 2;
      const fill = this.tiles[z.id];
      fill.style.backgroundImage = `url("${this.opts.asset(`tex/${code}-w.jpg`)}")`;
      fill.style.backgroundSize = `${100 / across}% auto`;
    }
    this.root.dataset.active = this.active || '';
  }

  setActive(zone) {
    this.active = zone;
    this.root.querySelectorAll('.viz-zone').forEach((b) => {
      b.classList.toggle('is-active', b.dataset.zone === zone);
    });
  }
}

function el(tag, cls) { const n = document.createElement(tag); n.className = cls; return n; }

function place(node, rect) {
  const [x, y, w, h] = rect;
  node.style.left = `${x * 100}%`;
  node.style.top = `${y * 100}%`;
  node.style.width = `${w * 100}%`;
  node.style.height = `${h * 100}%`;
}
