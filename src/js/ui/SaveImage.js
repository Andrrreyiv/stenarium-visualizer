// Сохранение картинки. Рисуем сцену заново на холсте в полном разрешении кадра,
// а не снимаем экран: так результат не зависит от размера окна.

export async function saveImage(scene, fg, model, opts) {
  const W = scene.width;
  const H = scene.height;
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d');

  const load = (src) => new Promise((res, rej) => {
    const i = new Image();
    i.crossOrigin = 'anonymous';
    i.onload = () => res(i);
    i.onerror = () => rej(new Error(`не загрузилось: ${src}`));
    i.src = src;
  });

  ctx.drawImage(await load(opts.asset('scene/bg.jpg')), 0, 0, W, H);

  for (const z of scene.zones) {
    const code = model.get(z.id);
    const item = opts.item(code);
    if (!item) continue;
    const tex = await load(opts.asset(`tex/${code}-w.jpg`));
    const [rx, ry, rw, rh] = z.rect;
    const x = rx * W;
    const y = ry * H;
    const w = rw * W;
    const h = rh * H;
    // Одна панель на зону, лишнее по краю обрезается. Повторять текстуру плиткой
    // нельзя: на рисунчатых артикулах вроде YB-3038C сетка стыков читалась насквозь,
    // и вместо образца материала посетитель видел плитку. То же правило в CSS зоны.
    const scale = Math.max(w / tex.width, h / tex.height);
    const dw = tex.width * scale;
    const dh = tex.height * scale;
    ctx.save();
    ctx.beginPath();
    ctx.rect(x, y, w, h);
    ctx.clip();
    ctx.drawImage(tex, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh);
    ctx.restore();
  }

  ctx.drawImage(await load(opts.asset('scene/shade.png')), 0, 0, W, H);
  const front = await load(opts.asset('scene/fg.png'));
  const [fx, fy, fw, fh] = fg.rect;
  ctx.drawImage(front, fx * W, fy * H, fw * W, fh * H);

  const blob = await new Promise((res) => canvas.toBlob(res, 'image/jpeg', 0.92));
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'stenarium-visualizer.jpg';
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
