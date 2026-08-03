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

# Геометрия рендера 1672x941. Замерена по перепадам яркости и проверена по срезам:
# канавки молдингов остаются ЗА пределами прямоугольников, поэтому рамки панелей
# видны поверх текстуры сами собой, без отдельного слоя.
SCENE_W, SCENE_H = 1672, 941
ZONES = {
    "left": (30, 82, 492, 725),
    "center": (528, 82, 1120, 725),
    "right": (1162, 82, 1626, 725),
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
    y0, y1 = 82, 725

    # Диван. Порог по яркости в одиночку не работает: затенённые места дивана темнее
    # порога, маска рвётся и сквозь неё проступает текстура. Поэтому порог + заливка
    # внутренних дырок + выбор одной самой крупной связной области.
    from scipy import ndimage
    # Полоса поиска дивана: строго до низа панелей. Ниже начинается пол, а он ТОЖЕ тёплый
    # (R-B около 66) и попадает в маску, утаскивая её на пол. Ниже панелей передний слой
    # не нужен вовсе: там текстуры нет и виден исходный фон.
    band = np.zeros(lum.shape, bool)
    band[520:y1 + 6, 360:1310] = True
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
    fg = np.dstack([base, m]).astype(np.uint8)[by0:by1, bx0:bx1]
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
            code = slug(f.name)
            im = Image.open(f).convert("RGB")
            for side, tag in ((900, "w"), (240, "t")):
                r = im.resize((side, side), Image.LANCZOS)
                r.save(TEX / f"{code}-{tag}.webp", "WEBP", quality=82, method=5)
                r.save(TEX / f"{code}-{tag}.jpg", "JPEG", quality=82, optimize=True)
            items.append({"code": code, "label": Path(f.name).stem.strip(), "url": ""})
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
        "zones": [
            {"id": zid, "title": ZONE_TITLES[zid],
             "rect": [x0 / SCENE_W, y0 / SCENE_H, (x1 - x0) / SCENE_W, (y1 - y0) / SCENE_H]}
            for zid, (x0, y0, x1, y1) in ZONES.items()
        ],
        "defaults": {z: first for z in ZONES},
        "tilesAcross": {"wood": 2, "stone": 2, "marble": 2, "mono": 1, "metal": 2, "fabric": 2},
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
