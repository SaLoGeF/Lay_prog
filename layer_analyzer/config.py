"""
Конфигурация приложения.
Все параметры алгоритма и пути собраны здесь —
менять настройки нужно только в этом файле.
"""

from pathlib import Path

# ── Пути ──────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}

# ── Параметры предобработки ───────────────────────────────────────────────────

GAMMA_CORRECTION = 2.0          # гамма-коррекция перед сегментацией

# ── Параметры сегментации ─────────────────────────────────────────────────────

N_CLASSES = 3                   # количество классов для multiotsu

# Радиус медианного фильтра (диск)
MEDIAN_DISK_RADIUS = 3          # для 1-го и 2-го слоёв
MEDIAN_DISK_RADIUS_L3 = 5       # для 3-го слоя

# Параметры морфологии
EROSION_DISK = 5
DILATION_DISK = 5
MIN_OBJECT_SIZE = 60_000        # минимальный размер объекта после erosion
CLOSING_DISK = 7

# Порог уровня при поиске контуров
CONTOUR_LEVEL_1 = 0.5
CONTOUR_LEVEL_2 = 0.6

# ── Параметры поиска границ (алгоритм Sike copy 2) ───────────────────────────
# Все коэффициенты перенесены из исходного скрипта без изменений.

# Распределение классов Multi-Otsu (3 класса)
SIKE_DISTRIBUTION_SIGMA = 30        # σ для гауссова сглаживания распределений по строкам

# Поиск диапазонов границ
SIKE_GRAD_THRESHOLD_FRAC = 0.3      # доля от пикового градиента для определения зоны спада/роста

# Ruptures (Binseg, model="l2")
SIKE_RUPTURES_BOUNDARY1_NBKPS = 1
SIKE_RUPTURES_BOUNDARY2_NBKPS = 3   # n_bkps=3, берём первые 2 break-points

# Уточнение границы 1
SIKE_BOUNDARY1_LEVEL_THRESHOLD = 0.99   # уровень доли чёрных пикселей для левой опоры гр.1

# Уточнение границы 2
SIKE_BOUNDARY2_LEFT_SEARCH_RANGE = 300  # окно поиска влево от bkp2
SIKE_BOUNDARY2_FLAT_RATIO = 0.1         # порог пологости градиента

# Точная граница 1 (верхние серые пиксели)
SIKE_PRECISE1_DROP_THRESHOLD = 20
SIKE_PRECISE1_MEDIAN_WINDOW = 71
SIKE_PRECISE1_SMOOTH_SIGMA = 15

# Точная граница 2 (верхние белые пиксели)
SIKE_PRECISE2_DROP_THRESHOLD = 20
SIKE_PRECISE2_MEDIAN_WINDOW = 71
SIKE_PRECISE2_SMOOTH_SIGMA = 25

# Подготовка маски слоя 3 (Multi-Otsu 4 классa)
SIKE_LAYER3_MEDIAN_SIZE = 3
SIKE_LAYER3_N_CLASSES = 4

# Точная граница 3 (верх плотного слоя в очищенной маске)
SIKE_PRECISE3_SMOOTH_SIGMA = 65
SIKE_PRECISE3_JUMP_THRESHOLD = 10
SIKE_PRECISE3_MAX_SPIKE_WIDTH = 300
SIKE_PRECISE3_FINAL_SMOOTH_SIGMA = 2

# ── Параметры анализа пористости ─────────────────────────────────────────────

PORE_MIN_RADIUS = 2
PORE_MAX_RADIUS = 60
PORE_RADIUS_STEP = 2
PORE_DIST_BIN_STEP = 1.0

# Шаг по x при сборе точек границы
BORDER_STEP_LARGE = 16          # для изображений >= 2048 px
BORDER_STEP_SMALL = 8           # для изображений < 2048 px

# Допуск фильтрации выбросов относительно высоты изображения
BORDER_FILTER_ABOVE = 0.03      # mean_y + shape[0] * 0.03
BORDER_FILTER_BELOW = 0.02      # mean_y - shape[0] * 0.02

# Допуск для нижней границы (в пикселях, абсолютный)
LOWER_BORDER_TOLERANCE = 30

# ── Параметры 3-го слоя (multiotsu с 4 классами) ─────────────────────────────

N_CLASSES_L3 = 4
SMALL_OBJECTS_L3 = 128          # удаление мелких объектов в 3-м слое

# ── Анализ трёхфазной границы (TPB) в слое 2 ────────────────────────────────
# Методика Auto-Post: Kent et al., Materials Characterization 226 (2025) 115201.

TPB_GRADIENT_HIST_SIGMA = 3     # сглаживание гистограммы градиента для поиска 2-го пика
TPB_GRADIENT_PEAK_HEIGHT = 0.05 # минимальная относительная высота пика
TPB_GRAD_SEARCH_MAX_FALLBACK = 0.30  # дефолтный верхний предел поиска порога
TPB_GRAD_SEARCH_MIN = 0.05      # нижний предел области поиска
TPB_GRAD_SEARCH_MAX_LIMIT = 0.5 # абсолютный верхний предел
TPB_GRAD_SEARCH_STEPS = 80      # количество шагов в скан-сетке порога градиента
TPB_PHASE_OTSU_CLASSES = 3      # классов Multi-Otsu на marker-average (3 фазы)

# ── Интерфейс ─────────────────────────────────────────────────────────────────

APP_TITLE = "Layer Analyzer"
WINDOW_MIN_WIDTH = 1400
WINDOW_MIN_HEIGHT = 800
PREVIEW_MAX_SIZE = (700, 580)   # максимальный размер превью (px)
THUMBNAIL_SIZE = (80, 60)       # размер миниатюры в списке файлов