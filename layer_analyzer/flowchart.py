"""
Блок-схема алгоритма анализа изображений ячейки ТОТЭ.
Зависимости: matplotlib
"""

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

matplotlib.rcParams["font.family"] = "DejaVu Sans"
matplotlib.rcParams["font.size"] = 9

# ── Цветовая палитра ──────────────────────────────────────────────────────────
C_IO       = "#5B9BD5"   # синий  — ввод/вывод
C_PROC     = "#70AD47"   # зелёный — процесс
C_DECISION = "#ED7D31"   # оранжевый — решение
C_RESULT   = "#7030A0"   # фиолетовый — результат
C_TEXT     = "white"

# ── Вспомогательные функции ───────────────────────────────────────────────────

def rect(ax, xy, w, h, text, color, fontsize=8.5, radius=0.015):
    x, y = xy
    box = FancyBboxPatch(
        (x - w / 2, y - h / 2), w, h,
        boxstyle=f"round,pad=0.01,rounding_size={radius}",
        linewidth=0.8,
        edgecolor="white",
        facecolor=color,
        zorder=3,
    )
    ax.add_patch(box)
    ax.text(
        x, y, text,
        ha="center", va="center",
        color=C_TEXT, fontsize=fontsize,
        wrap=True, zorder=4,
        multialignment="center",
    )


def diamond(ax, xy, w, h, text, color, fontsize=8.5):
    x, y = xy
    dx, dy = w / 2, h / 2
    coords = [(x, y + dy), (x + dx, y), (x, y - dy), (x - dx, y)]
    poly = plt.Polygon(coords, closed=True,
                       linewidth=0.8, edgecolor="white",
                       facecolor=color, zorder=3)
    ax.add_patch(poly)
    ax.text(x, y, text, ha="center", va="center",
            color=C_TEXT, fontsize=fontsize, zorder=4, multialignment="center")


def arrow(ax, x, y1, y2, label="", label_side="right"):
    ax.annotate(
        "", xy=(x, y2), xytext=(x, y1),
        arrowprops=dict(arrowstyle="-|>", color="#444444",
                        lw=1.2, mutation_scale=12),
        zorder=2,
    )
    if label:
        lx = x + 0.03 if label_side == "right" else x - 0.03
        ha = "left" if label_side == "right" else "right"
        mid = (y1 + y2) / 2
        ax.text(lx, mid, label, ha=ha, va="center",
                fontsize=7.5, color="#333333", zorder=5)


def harrow(ax, x1, x2, y, label="", label_pos="top"):
    ax.annotate(
        "", xy=(x2, y), xytext=(x1, y),
        arrowprops=dict(arrowstyle="-|>", color="#444444",
                        lw=1.2, mutation_scale=12),
        zorder=2,
    )
    if label:
        mx = (x1 + x2) / 2
        dy = 0.015 if label_pos == "top" else -0.015
        ax.text(mx, y + dy, label, ha="center", va="bottom" if label_pos == "top" else "top",
                fontsize=7.5, color="#333333", zorder=5)


def line(ax, x1, y1, x2, y2):
    ax.plot([x1, x2], [y1, y2], color="#444444", lw=1.2, zorder=2)


# ── Компоновка блоков ─────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(7, 13))
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")

CX   = 0.50   # центральная ось x
W    = 0.44   # ширина прямоугольника
H    = 0.048  # высота прямоугольника
DH   = 0.055  # высота ромба
GAP  = 0.072  # шаг по вертикали

# Y-координаты блоков сверху вниз
y = {}
y["start"]      = 0.960
y["load"]       = y["start"]      - GAP
y["crop_dec"]   = y["load"]       - GAP * 1.1
y["autocrop"]   = y["crop_dec"]   - GAP
y["manualcrop"] = y["autocrop"]          # тот же Y, смещён по X
y["gamma"]      = y["autocrop"]   - GAP
y["roi"]        = y["gamma"]      - GAP
y["profile"]    = y["roi"]        - GAP
y["global"]     = y["profile"]    - GAP
y["local"]      = y["global"]     - GAP
y["smooth"]     = y["local"]      - GAP
y["metrics"]    = y["smooth"]     - GAP
y["report"]     = y["metrics"]    - GAP
y["end"]        = y["report"]     - GAP * 0.8

# 1. Начало
rect(ax, (CX, y["start"]), 0.25, 0.038,
     "НАЧАЛО", C_IO, fontsize=9)

# 2. Загрузка
arrow(ax, CX, y["start"] - 0.019, y["load"] + 0.024)
rect(ax, (CX, y["load"]), W, H,
     "Загрузка изображения\n(ImageLoader)", C_IO)

# 3. Решение: обрезка
arrow(ax, CX, y["load"] - 0.024, y["crop_dec"] + DH / 2)
diamond(ax, (CX, y["crop_dec"]), 0.42, DH,
        "Автоматическая\nобрезка?", C_DECISION)

# 3a. Авто-обрезка (левая ветка)
XL = CX - 0.25
arrow(ax, CX, y["crop_dec"] - DH / 2, y["autocrop"] + H / 2)
rect(ax, (CX, y["autocrop"]), W, H,
     "Автоматическое удаление\nинформационной полосы микроскопа", C_PROC)

# 3b. Ручная обрезка (правая ветка)
XR = CX + 0.28
line(ax, CX + 0.21, y["crop_dec"], XR, y["crop_dec"])
line(ax, XR, y["crop_dec"], XR, y["autocrop"])
ax.annotate("", xy=(XR - 0.001, y["autocrop"] + H / 2),
            xytext=(XR, y["autocrop"]),
            arrowprops=dict(arrowstyle="-|>", color="#444444",
                            lw=1.2, mutation_scale=12), zorder=2)
ax.text(CX + 0.225, y["crop_dec"] + 0.012, "Да", fontsize=7.5, color="#333333")
ax.text(CX + 0.225, y["crop_dec"] - 0.022, "Нет", fontsize=7.5, color="#333333")
rect(ax, (XR, y["autocrop"]), 0.30, H,
     "Ручная обрезка\nпо заданным координатам", C_PROC, fontsize=8)

# Стрелка из 3b вниз к гамме: горизонтальная линия к центру
line(ax, XR, y["autocrop"] - H / 2, XR, y["gamma"])
line(ax, XR, y["gamma"], CX + W / 2, y["gamma"])

# 4. Гамма-коррекция
arrow(ax, CX, y["autocrop"] - H / 2, y["gamma"] + H / 2)
rect(ax, (CX, y["gamma"]), W, H,
     "Гамма-коррекция изображения", C_PROC)

# 5. Выделение ROI
arrow(ax, CX, y["gamma"] - H / 2, y["roi"] + H / 2)
rect(ax, (CX, y["roi"]), W, H,
     "Маскирование краёв (ROI):\nудаление нерелевантных областей", C_PROC)

# 6. Профили яркости
arrow(ax, CX, y["roi"] - H / 2, y["profile"] + H / 2)
rect(ax, (CX, y["profile"]), W, H,
     "Вычисление строчных профилей\nсредней яркости и СКО по столбцам", C_PROC)

# 7. Глобальные границы
arrow(ax, CX, y["profile"] - H / 2, y["global"] + H / 2)
rect(ax, (CX, y["global"]), W, H,
     "Определение глобальных границ слоёв\nпо градиенту сглаженного профиля", C_PROC)

# 8. Локальное уточнение
arrow(ax, CX, y["global"] - H / 2, y["local"] + H / 2)
rect(ax, (CX, y["local"]), W, H,
     "Локальное поколоночное уточнение\nграниц (скользящая полоса)", C_PROC)

# 9. Сглаживание контуров
arrow(ax, CX, y["local"] - H / 2, y["smooth"] + H / 2)
rect(ax, (CX, y["smooth"]), W, H,
     "Сглаживание контуров границ\n(гауссова фильтрация)", C_PROC)

# 10. Морфометрические метрики
arrow(ax, CX, y["smooth"] - H / 2, y["metrics"] + H / 2)
rect(ax, (CX, y["metrics"]), W, H,
     "Расчёт морфометрических параметров:\nтолщина, СКО, коэффициент вариации", C_RESULT)

# 11. Формирование отчёта
arrow(ax, CX, y["metrics"] - H / 2, y["report"] + H / 2)
rect(ax, (CX, y["report"]), W, H,
     "Формирование отчёта и\nгалереи изображений (AnalysisReport)", C_IO)

# 12. Конец
arrow(ax, CX, y["report"] - H / 2, y["end"] + 0.019)
rect(ax, (CX, y["end"]), 0.25, 0.038,
     "КОНЕЦ", C_IO, fontsize=9)

# ── Легенда ───────────────────────────────────────────────────────────────────
legend_items = [
    mpatches.Patch(facecolor=C_IO,       label="Ввод / Вывод"),
    mpatches.Patch(facecolor=C_PROC,     label="Процесс обработки"),
    mpatches.Patch(facecolor=C_DECISION, label="Условие"),
    mpatches.Patch(facecolor=C_RESULT,   label="Вычисление метрик"),
]
ax.legend(handles=legend_items, loc="lower left",
          bbox_to_anchor=(0.01, 0.01), fontsize=8,
          framealpha=0.85, edgecolor="#aaaaaa")

fig.patch.set_facecolor("#F5F5F5")
plt.title("Блок-схема алгоритма анализа изображений ячейки ТОТЭ",
          fontsize=11, fontweight="bold", pad=10)
plt.tight_layout()
plt.savefig("flowchart.png", dpi=200, bbox_inches="tight",
            facecolor=fig.get_facecolor())
print("Сохранено: flowchart.png")
plt.show()
