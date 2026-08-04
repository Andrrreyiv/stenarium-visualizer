// Разбор и проверка каталога. Каталог приходит данными, поэтому валидируем его здесь,
// а не надеемся на аккуратность таблицы.

export function validateCatalog(raw) {
  if (!raw || !Array.isArray(raw.series) || raw.series.length === 0) {
    throw new Error('Каталог пуст или не разобран');
  }
  const seen = new Set();
  const series = raw.series.map((s) => {
    if (!s.id || !s.title) throw new Error('У серии нет id или названия');
    if (!Array.isArray(s.items) || s.items.length === 0) {
      throw new Error(`Серия «${s.title}» без панелей`);
    }
    const items = s.items.map((it) => {
      if (!it.code) throw new Error(`В серии «${s.title}» панель без артикула`);
      if (seen.has(it.code)) throw new Error(`Артикул ${it.code} встречается дважды`);
      seen.add(it.code);
      // Ссылка на товар необязательна: каталог на сайте ещё синхронизируют.
      // Пусто означает, что кнопка перехода просто не показывается.
      // Имя и артикул показываются раздельно: имя крупно, артикул под ним мельче.
      // Артикул есть не у всех: часть расцветок в каталоге не заведена и печатается
      // под заказ. Пустое поле здесь означает именно это, а не потерю данных.
      return {
        code: it.code,
        name: it.name || it.code,
        article: it.article || '',
        url: it.url || '',
        series: s.id,
      };
    });
    return { id: s.id, title: s.title, items };
  });
  return { series };
}

export function findItem(catalog, code) {
  for (const s of catalog.series) {
    const hit = s.items.find((i) => i.code === code);
    if (hit) return hit;
  }
  return null;
}
