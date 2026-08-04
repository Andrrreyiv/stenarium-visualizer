"""Выравнивание рамок на рендере интерьера.

На исходном рендере центральная рамка шире боковых: внутренние поля 462, 592, 464 px.
Из-за этого три зоны выбора не могут быть равными, а клиенту нужны равные.
Подогнать прямоугольники под рамку нельзя (внутри центрального молдинга осталась бы
серая полоса), поэтому двигаем сам молдинг: обе вертикальные планки центральной рамки
уходят внутрь на 65 px, внутреннее поле становится 462 px, как у боковых.

Замеры по рендеру 1672x941 (яркость по полосе y=120..500):
  левая планка центра   x 517..535, снаружи 143.5, внутри 140.4
  правая планка центра  x 1120..1144, внутри 119.3, снаружи 116.1
  верхняя планка        y 66..80 (одинаково у всех трёх рамок)
Нижние углы центральной рамки закрыты диваном (он начинается с y=555), поэтому правка
идёт только по стене выше дивана и выше плинтуса.

Приём: строим подложку без планок (планки вычищены интерполяцией), считаем ОТНОШЕНИЕ
рендера к подложке и переносим отношение на новое место. Отношение, а не пиксели: стена
по горизонтали темнеет, перенос пикселей как есть дал бы ступеньку яркости, а перенос
отношения сажает планку на местный уровень стены.

ВАЖНО: подложка строится интерполяцией, а не размытием. Размытие не совпадает с
оригиналом там, где планок нет, и на границе правки вылезал горизонтальный шов.
Интерполяция по краям совпадает с оригиналом точно, поэтому границ не видно.
"""
import numpy as np
from scipy import ndimage

SHIFT = 65

# Полоса-источник: планка плюс запас, на котором отношение уже равно единице.
SRC_LEFT = (513, 540)
SRC_RIGHT = (1116, 1149)
DST_LEFT = (SRC_LEFT[0] + SHIFT, SRC_LEFT[1] + SHIFT)
DST_RIGHT = (SRC_RIGHT[0] - SHIFT, SRC_RIGHT[1] - SHIFT)
# Стирается начисто: старое место планки и бывшее поле панели, ставшее промежутком.
ERASE_LEFT = (512, DST_LEFT[0])
ERASE_RIGHT = (DST_RIGHT[1], 1149)

WIN = (480, 1180)
Y_TOP = 50
# Низ стены: ниже идёт плинтус и пол, туда правка заходить не должна.
Y_BOT = 735
H_BORDER = (62, 86)
# Чистка вертикальных планок в подложке. Диапазоны широкие нарочно: перепад между
# полем панели и промежутком между рамок размазывается на всю ширину промежутка и
# перестаёт читаться как край.
FILL_LEFT = dict(fill=(514, 578), lsrc=(506, 514), rsrc=(578, 586))
FILL_RIGHT = dict(fill=(1084, 1145), lsrc=(1076, 1084), rsrc=(1145, 1151))


def sofa_mask(arr):
    """Силуэт дивана тем же признаком, что и в make-assets: яркость ИЛИ теплота цвета."""
    lum = arr.mean(axis=2)
    warm = arr[:, :, 0] - arr[:, :, 2]
    band = np.zeros(lum.shape, bool)
    band[520:800, 360:1310] = True
    rough = ((lum > 175) | (warm > 14)) & band
    filled = ndimage.binary_fill_holes(rough)
    lbl, n = ndimage.label(filled)
    if not n:
        return filled
    sizes = ndimage.sum(filled, lbl, range(1, n + 1))
    m = lbl == (int(np.argmax(sizes)) + 1)
    m = ndimage.binary_closing(m, np.ones((9, 9)))
    # Запас 3x3, как у переднего слоя в make-assets: больший запас оставлял над кромкой
    # дивана незакрашенный огрызок старой планки.
    return ndimage.binary_dilation(m, np.ones((3, 3)))


def _fill_rows(a, y0, y1, pad=6):
    """Убрать горизонтальную планку: вертикальная интерполяция между чистыми строками."""
    top = a[y0 - pad:y0].mean(axis=0)
    bot = a[y1:y1 + pad].mean(axis=0)
    n = y1 - y0
    for i in range(n):
        t = (i + 1) / (n + 1)
        a[y0 + i] = top * (1 - t) + bot * t


def _fill_cols(a, fill, lsrc, rsrc):
    """Убрать вертикальную планку: горизонтальная интерполяция, край в край с оригиналом."""
    left = a[:, lsrc[0]:lsrc[1]].mean(axis=1)
    right = a[:, rsrc[0]:rsrc[1]].mean(axis=1)
    n = fill[1] - fill[0]
    for i in range(n):
        t = (i + 1) / (n + 1)
        a[:, fill[0] + i] = left * (1 - t) + right * t


def equalize_center_frame(img):
    """img: PIL RGB рендера 1672x941 -> PIL RGB с равными рамками."""
    from PIL import Image

    arr = np.asarray(img).astype(np.float32)
    h, _, _ = arr.shape
    sofa = sofa_mask(arr)

    x0, x1 = WIN
    win = arr[:, x0:x1]
    sofa_win = sofa[:, x0:x1]

    base = win.copy()
    _fill_rows(base, H_BORDER[0], H_BORDER[1])
    for f in (FILL_LEFT, FILL_RIGHT):
        _fill_cols(base, [v - x0 for v in f["fill"]],
                   [v - x0 for v in f["lsrc"]], [v - x0 for v in f["rsrc"]])

    ratio = win / np.maximum(base, 1.0)
    new_ratio = ratio.copy()
    for a, b in (ERASE_LEFT, ERASE_RIGHT):
        new_ratio[:, a - x0:b - x0] = 1.0
    for (sa, sb), (da, db) in ((SRC_LEFT, DST_LEFT), (SRC_RIGHT, DST_RIGHT)):
        new_ratio[:, da - x0:db - x0] = ratio[:, sa - x0:sb - x0]

    out = np.clip(base * new_ratio, 0, 255)

    res = arr.copy()
    band = np.zeros((h, x1 - x0), bool)
    band[Y_TOP:Y_BOT, :] = True
    band &= ~sofa_win
    res_win = res[:, x0:x1]
    res_win[band] = out[band]
    res[:, x0:x1] = res_win
    return Image.fromarray(np.clip(res, 0, 255).astype(np.uint8), "RGB")

