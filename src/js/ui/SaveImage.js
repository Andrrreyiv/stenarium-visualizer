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
    const across = scene.tilesAcross[item.series] || 2;
    const side = w / across;
    ctx.save();
    ctx.beginPath();
    ctx.rect(x, y, w, h);
    ctx.clip();
    for (let ty = 0; ty < h; ty += side) {
      for (let tx = 0; tx < w; tx += side) ctx.drawImage(tex, x + tx, y + ty, side, side);
    }
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
