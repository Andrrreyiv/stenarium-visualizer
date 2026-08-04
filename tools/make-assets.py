"""Подготовка ассетов визуализатора из исходников клиента (Я.Диск).

1. Скачивает рендер интерьера и текстуры из публичной папки.
2. Режет рендер на слои: фон, карта света (multiply), передний слой с диваном.
3. Пересчитывает текстуры в 900px (стена) и 240px (плитка меню), webp + jpeg-фолбэк.

Запуск: python tools/make-assets.py [--skip-download]
Скрипт разовый, в рантайм визуализатора не входит. Python выбран из-за PIL.
"""
import json
import re
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

PUBLIC_KEY = "https://disk.yandex.ru/d/RG1uLymsyBig9g"
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "assets" / "_raw"
SCENE = ROOT / "assets" / "scene"
TEX = ROOT / "assets" / "tex"

# Геометрия рендера 1672x941.
# Клиент попросил облицевать стену целиком: панели идут по всей длине, а не лежат
# внутри выемок молдинга. Поэтому три равные зоны встык закрывают стену от карниза
# до пола, а рамки исходного рендера уходят ПОД текстуру и в кадре не участвуют.
# Границы стены замерены по кадру: карниз кончается на y=47..48 ровно по всей ширине,
# стык с полом на y=767 (ниже теплота R-B прыгает с 14 до 55, это паркет).
SCENE_W, SCENE_H = 1672, 941
WALL_TOP, WALL_BOTTOM = 48, 767
ZONES = {
    "left": (0, WALL_TOP, round(SCENE_W / 3), WALL_BOTTOM),
    "center": (round(SCENE_W / 3), WALL_TOP, round(2 * SCENE_W / 3), WALL_BOTTOM),
    "right": (round(2 * SCENE_W / 3), WALL_TOP, SCENE_W, WALL_BOTTOM),
}
ZONE_TITLES = {"left": "Левая", "center": "Центральная", "right": "Правая"}

SERIES_ORDER = [
    ("Деревянная серия", "wood", "Дерево"),
    ("Каменная серия", "stone", "Камень"),
    ("Гибкий мрамор", "marble", "Гибкий мрамор"),
    ("Mono серия", "mono", "Mono"),
    ("Металлическая серия", "metal", "Металл"),
    ("Тканевая серия", "fabric", "Ткань"),
]


def api(endpoint, **params):
    params["public_key"] = PUBLIC_KEY
    url = f"https://cloud-api.yandex.net/v1/disk/public/{endpoint}?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=90) as r:
        return json.load(r)


def fetch(path):
    href = api("resources/download", path=path)["href"]
    req = urllib.request.Request(href, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def slug(name):
    """Имя файла -> идентификатор для URL. Хвостовые пробелы трёх файлов Mono убираются здесь."""
    s = Path(name).stem.strip().replace(" ", "-")
    return re.sub(r"[^A-Za-z0-9\-_А-Яа-яЁё]", "", s)


# Имя файла у клиента: «Название (АРТИКУЛ).png». Артикул есть не у всех: у восьми
# позиций Mono его нет вовсе, такие расцветки печатаются под заказ.
ARTICLE_RE = re.compile(r"^(?P<name>.+?)\s*\((?P<art>[^)]*)\)?\s*$")


def parse_item(filename):
    """«Дуб (YB-3031C).png» -> («Дуб», «YB-3031C»). Без скобок артикул пустой."""
    stem = Path(filename).stem.strip()
    m = ARTICLE_RE.match(stem)
    if not m:
        return stem, ""
    # Чистим артикул от всего, кроме букв, цифр и дефиса. Так лечатся три огреха
    # в исходных именах, замеченные при разборе 04.08.2026:
    #   «Жемчужный рассвет (YB-4012D₽» — закрывающая скобка набрана знаком рубля
    #   «Беленый дуб (YB -4087D)» и «Black Statuario (KL 8264)» — пробел внутри артикула
    return m.group("name").strip(), re.sub(r"[^A-Za-z0-9\-]", "", m.group("art"))


def download_all():
    RAW.mkdir(parents=True, exist_ok=True)
    jobs = []
    root = api("resources", limit=500)
    for item in root["_embedded"]["items"]:
        if item["type"] == "file":
            jobs.append((item["path"], RAW / item["name"]))
        else:
            sub = api("resources", path=item["path"], limit=500)
            folder = RAW / item["name"]
            folder.mkdir(exist_ok=True)
            for f in sub["_embedded"]["items"]:
                if f["type"] == "file":
                    jobs.append((f["path"], folder / f["name"]))

    def one(job):
        src, dst = job
        if dst.exists() and dst.stat().st_size > 0:
            return dst
        dst.write_bytes(fetch(src))
        return dst

    with ThreadPoolExecutor(6) as ex:
        list(ex.map(one, jobs))
    print(f"скачано файлов: {len(jobs)}")


def build_scene():
    """Рендер -> три слоя: bg.jpg, shade.png (multiply), fg.png (диван)."""
    SCENE.mkdir(parents=True, exist_ok=True)
    src = Image.open(RAW / "IMG_0037.png").convert("RGB")
    assert src.size == (SCENE_W, SCENE_H), f"неожиданный размер рендера: {src.size}"
    src.save(SCENE / "bg.jpg", "JPEG", quality=88, optimize=True)

    arr = np.asarray(src).astype(np.float32)
    lum = arr.mean(axis=2)
    y0, y1 = WALL_TOP, WALL_BOTTOM

    # Диван. Порог по яркости в одиночку не работает: затенённые места дивана темнее
    # порога, маска рвётся и сквозь неё проступает текстура. Поэтому порог + заливка
    # внутренних дырок + выбор одной самой крупной связной области.
    from scipy import ndimage
    # Полоса поиска дивана: строго до низа панелей. Ниже начинается пол, а он ТОЖЕ тёплый
    # (R-B около 66) и попадает в маску, утаскивая её на пол. Ниже панелей передний слой
    # не нужен вовсе: там текстуры нет и виден исходный фон.
    band = np.zeros(lum.shape, bool)
    # Нижняя граница строго по низу стены. Раньше был запас в 6 px, и он был безвреден,
    # пока стена кончалась выше пола. Теперь низ зоны совпадает со стыком, и запас
    # затаскивал в маску полосу тёплого паркета через всю ширину кадра.
    band[520:y1, 360:1310] = True
    # Признак дивана: не яркость, а теплота цвета. Замер по кадру: у серой стены R-B
    # держится в диапазоне 9..11 по всей площади панелей, у обивки дивана медиана 24.
    # По яркости они пересекаются (низ дивана 124 против стены 110), по теплоте нет.
    warm = arr[:, :, 0] - arr[:, :, 2]
    # Один признак диван не покрывает. Замер по кадру:
    #   верх спинки  яркость 234, но нейтрален по цвету (R-B = 8)
    #   низ дивана   тёплый (R-B 31..40), но тёмный (яркость 124)
    #   стена        яркость 79..149, R-B стабильно 8..11
    # Поэтому берём объединение: заметно ярче любой стены ИЛИ заметно теплее любой стены.
    rough = ((lum > 175) | (warm > 14)) & band
    filled_mask = ndimage.binary_fill_holes(rough)
    lbl, n = ndimage.label(filled_mask)
    if n:
        sizes = ndimage.sum(filled_mask, lbl, range(1, n + 1))
        sofa_full = lbl == (int(np.argmax(sizes)) + 1)
    else:
        sofa_full = filled_mask
    sofa_full = ndimage.binary_closing(sofa_full, np.ones((9, 9)))
    # Заливка дырок не берёт теневую складку между сиденьем и спинкой: она тянется во всю
    # ширину дивана и не замкнута. Диван по каждому столбцу сплошной, поэтому заполняем
    # промежуток между верхним и нижним найденным пикселем столбца. Для такого силуэта точно.
    cols = np.where(sofa_full.any(axis=0))[0]
    tops = np.array([np.where(sofa_full[:, x])[0].min() for x in cols], float)
    bots = np.array([np.where(sofa_full[:, x])[0].max() for x in cols], float)
    # Границу сглаживаем по столбцам, иначе край спинки выходит рваным: сглаживание
    # пикселей на кромке даёт то попадание, то промах, и силуэт получается пилой.
    tops = ndimage.median_filter(tops, size=15)
    bots = ndimage.median_filter(bots, size=15)
    sofa_full[:] = False
    for i, x in enumerate(cols):
        sofa_full[int(tops[i]):int(bots[i]) + 1, x] = True
    sofa_full = ndimage.binary_dilation(sofa_full, np.ones((3, 3)))

    # Для карты света нужна только та часть дивана, что попадает в полосу панелей.
    sofa = np.zeros(lum.shape, bool)
    sofa[y0:y1, :] = sofa_full[y0:y1, :]

    # Карта света. Пиксели дивана заменяем медианой столбца, иначе на его месте останется
    # светлое пятно. Дальше сильное размытие: нужен плавный градиент, а не детали.
    filled = lum.copy()
    masked = np.where(~sofa, lum, np.nan)[y0:y1, :]
    per_col = np.nanmedian(masked, axis=0)
    per_col = np.nan_to_num(per_col, nan=float(np.nanmedian(per_col)))
    ys, xs = np.where(sofa)
    filled[ys, xs] = per_col[xs]

    # Канавки молдингов теперь ВНУТРИ облицованной зоны, и раньше они просто не попадали
    # в кадр. Слабое размытие отпечатало бы их тёмными полосами прямо по текстуре, а
    # сильное съело бы контактную тень за диваном. Поэтому убираем их адресно.
    # Вертикальные канавки (ширина до 28 px) уводит медиана ПОПЕРЁК: окно шире полосы,
    # поэтому линия уходит, а перепад света вдоль стены и тень за диваном остаются.
    filled = ndimage.median_filter(filled, size=(1, 71), mode="nearest")
    # Горизонтальные планки рамок медиана поперёк не берёт: они лежат вдоль окна.
    # Стираем их интерполяцией между чистыми строками над и под планкой.
    for ry0, ry1 in ((62, 88), (712, 733)):
        top = filled[ry0 - 8:ry0].mean(axis=0)
        bot = filled[ry1:ry1 + 8].mean(axis=0)
        for i in range(ry1 - ry0):
            t = (i + 1) / (ry1 - ry0 + 1)
            filled[ry0 + i] = top * (1 - t) + bot * t

    light = Image.fromarray(np.clip(filled, 0, 255).astype(np.uint8), "L")
    # Размытие слабое: сильное съедало контактную тень за диваном, а она нужна ЗДЕСЬ,
    # в множительном слое. Стена ровная, поэтому собственного шума она сюда не приносит.
    light = light.filter(ImageFilter.GaussianBlur(6))
    la = np.asarray(light).astype(np.float32)

    inside = np.zeros(la.shape, bool)
    for x0, zy0, x1, zy1 in ZONES.values():
        inside[zy0:zy1, x0:x1] = True
    ref = float(np.percentile(la[inside], 97))
    ratio = np.clip(la / max(ref, 1.0), 0.0, 1.0)

    alpha = np.clip((1.0 - ratio) * 255.0, 0, 255).astype(np.uint8)
    shade = np.zeros((SCENE_H, SCENE_W, 4), np.uint8)
    shade[..., 3] = alpha
    shade[~inside, 3] = 0
    Image.fromarray(shade, "RGBA").save(SCENE / "shade.png", optimize=True)

    # Передний слой: ТОЛЬКО силуэт дивана. Контактная тень живёт в множительном слое.
    # Класть её сюда нельзя: слой рисует пиксели серой стены поверх текстуры, и вместо
    # тени получается серый ореол по контуру. Обрезаем по габаритам ради веса.
    # Альфа мягкая, а не бинарная. У обивки букле край пушистый: замер по оригиналу даёт
    # дрожание силуэта в +-3 пикселя от столбца к столбцу. Жёсткий порог превращает ворс
    # в рваную кромку. Плавный переход по теплоте цвета оставляет край краем ткани.
    # Мягкий переход разрешён ТОЛЬКО в узкой полосе вокруг силуэта. Иначе он вылезает на
    # стену над спинкой: там лежит тёплый подсвет, отражённый от кремовой обивки, и он
    # проходит порог по теплоте. В кадре это выглядело как рваная светлая кайма по дереву.
    near = ndimage.binary_dilation(sofa_full, np.ones((9, 9))).astype(np.float32)
    # Мягкий переход считаем по ТОМУ ЖЕ объединённому признаку, что и грубую маску.
    # Только по теплоте нельзя: верх спинки нейтрален по цвету, и там альфа падала в ноль,
    # из-за чего по верхней кромке проступала полоска текстуры.
    score = np.maximum((lum - 155.0) / 25.0, (warm - 11.0) / 9.0)
    soft = np.clip(score, 0.0, 1.0) * band * near
    core = ndimage.binary_erosion(sofa_full, np.ones((7, 7))).astype(np.float32)
    mask = np.maximum(core, soft) * 255.0
    mask = np.asarray(
        Image.fromarray(mask.astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(0.6))
    ).astype(np.float32)
    m = np.clip(mask, 0, 255).astype(np.uint8)

    ys, xs = np.where(m > 0)
    bx0, bx1, by0, by1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
    # RGB переднего слоя берём из уже пересжатого bg.jpg, а не из оригинала: иначе на
    # полупрозрачных краях накладываются пиксели двух разных кодировок и виден габарит.
    base = np.asarray(Image.open(SCENE / "bg.jpg").convert("RGB"))
    # На полупрозрачной кромке цвет нельзя брать из фона: под текстурой там серая стена,
    # и вместо ворса букле по контуру дивана шла светлая кайма. Особенно заметно теперь,
    # когда тёмная текстура доходит до самого дивана. Поэтому на кромку растягиваем цвет
    # ближайшего непрозрачного пикселя самого дивана: край смешивается уже с текстурой.
    core_rgb = m >= 250
    nearest = ndimage.distance_transform_edt(~core_rgb, return_distances=False, return_indices=True)
    filled_rgb = base[nearest[0], nearest[1]]
    rgb = np.where(core_rgb[..., None], base, filled_rgb)
    fg = np.dstack([rgb, m]).astype(np.uint8)[by0:by1, bx0:bx1]
    Image.fromarray(fg, "RGBA").save(SCENE / "fg.png", optimize=True)
    (SCENE / "fg.json").write_text(json.dumps(
        {"rect": [bx0 / SCENE_W, by0 / SCENE_H,
                  (bx1 - bx0) / SCENE_W, (by1 - by0) / SCENE_H]}, indent=2), encoding="utf-8")
    print(f"  fg bbox: x {bx0}..{bx1}  y {by0}..{by1}")

    for f in ("bg.jpg", "shade.png", "fg.png"):
        print(f"  {f}: {(SCENE / f).stat().st_size / 1024:.0f} КБ")


def build_textures():
    TEX.mkdir(parents=True, exist_ok=True)
    catalog = {"series": []}
    for folder, sid, title in SERIES_ORDER:
        d = RAW / folder
        if not d.is_dir():
            print(f"  ПРОПУЩЕНА серия {folder}: папки нет")
            continue
        items = []
        for f in sorted(d.glob("*.png")):
            name, article = parse_item(f.name)
            # Код позиции держим на артикуле: он не меняется при переименовании файла,
            # совпадает с прежними кодами и потому не ломает уже разосланные ссылки.
            # Без артикула другого устойчивого ключа нет, берём имя.
            code = slug(article) if article else slug(name)
            im = Image.open(f).convert("RGB")
            for side, tag in ((900, "w"), (240, "t")):
                r = im.resize((side, side), Image.LANCZOS)
                r.save(TEX / f"{code}-{tag}.webp", "WEBP", quality=82, method=5)
                r.save(TEX / f"{code}-{tag}.jpg", "JPEG", quality=82, optimize=True)
            items.append({"code": code, "name": name, "article": article, "url": ""})
        catalog["series"].append({"id": sid, "title": title, "items": items})
        print(f"  {title}: {len(items)}")
    return catalog


def main():
    if "--skip-download" not in sys.argv:
        download_all()
    print("сцена:")
    build_scene()
    print("текстуры:")
    catalog = build_textures()

    first = catalog["series"][0]["items"][0]["code"]
    scene_cfg = {
        "width": SCENE_W,
        "height": SCENE_H,
        # Доли пишем точными третями, а не через округлённые пиксели: иначе крайние
        # зоны отличались бы от средней на пиксель, и равенство перестало бы быть равенством.
        "zones": [
            {"id": zid, "title": ZONE_TITLES[zid],
             "rect": [i / 3, WALL_TOP / SCENE_H, 1 / 3, (WALL_BOTTOM - WALL_TOP) / SCENE_H]}
            for i, zid in enumerate(ZONES)
        ],
        "defaults": {z: first for z in ZONES},
        "disclaimer": "Размер панелей и итоговый вид могут отличаться от реальных.",
    }
    (ROOT / "src" / "config" / "scene.json").write_text(
        json.dumps(scene_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "src" / "config" / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum(len(s["items"]) for s in catalog["series"])
    size = sum(f.stat().st_size for f in TEX.glob("*")) / 1048576
    print(f"\nвсего текстур: {total}")
    print(f"вес каталога после пересчёта: {size:.1f} МБ")


if __name__ == "__main__":
    main()
