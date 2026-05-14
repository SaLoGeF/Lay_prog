"""
Поиск трёх границ слоёв (алгоритм Sike copy 2.py).

Шаги:
  1. Multi-Otsu (3 класса) → распределения долей чёрных/белых по строкам.
  2. Грубое определение диапазонов границ (градиент + ruptures.Binseg).
  3. Точная граница 1 — верхние серые пиксели в [b1_left, b1_right].
  4. Точная граница 2 — верхние белые пиксели в [b2_left, b2_right].
  5. ROI слоя 3 (Multi-Otsu 4 класса) → бинарная маска плотных частиц.
  6. Точная граница 3 — верхние пиксели маски + срез вертикальных скачков.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import skimage as ski
from scipy.ndimage import gaussian_filter1d, median_filter
from scipy.signal import find_peaks
from skimage import filters, measure, morphology, util

import ruptures as rpt

from config import (
    SIKE_BOUNDARY1_LEVEL_THRESHOLD,
    SIKE_BOUNDARY2_FLAT_RATIO,
    SIKE_BOUNDARY2_LEFT_SEARCH_RANGE,
    SIKE_DISTRIBUTION_SIGMA,
    SIKE_GRAD_THRESHOLD_FRAC,
    SIKE_LAYER3_MEDIAN_SIZE,
    SIKE_LAYER3_N_CLASSES,
    SIKE_PRECISE1_DROP_THRESHOLD,
    SIKE_PRECISE1_MEDIAN_WINDOW,
    SIKE_PRECISE1_SMOOTH_SIGMA,
    SIKE_PRECISE2_DROP_THRESHOLD,
    SIKE_PRECISE2_MEDIAN_WINDOW,
    SIKE_PRECISE2_SMOOTH_SIGMA,
    SIKE_PRECISE3_FINAL_SMOOTH_SIGMA,
    SIKE_PRECISE3_JUMP_THRESHOLD,
    SIKE_PRECISE3_MAX_SPIKE_WIDTH,
    SIKE_PRECISE3_SMOOTH_SIGMA,
    SIKE_RUPTURES_BOUNDARY1_NBKPS,
    SIKE_RUPTURES_BOUNDARY2_NBKPS,
)


@dataclass
class BoundaryDetectionResult:
    x: np.ndarray
    y0: np.ndarray  # верх слоя 1 (граница 1, точная — верхние серые пиксели)
    y1: np.ndarray  # верх слоя 2 (граница 2, точная — верхние белые пиксели)
    y2: np.ndarray  # верх слоя 3 (граница 3, точная — верх плотной маски)


class LayerDetector:

    @staticmethod
    def detect_boundaries(image: np.ndarray) -> BoundaryDetectionResult:
        gray = LayerDetector._to_float_gray(image)
        height, width = gray.shape

        analysis = LayerDetector._analyze_multithreshold_distribution(gray)
        ranges = LayerDetector._find_boundary_ranges(analysis, height)

        y0_line = LayerDetector._find_boundary1_precise(analysis, ranges, width)
        y1_line = LayerDetector._find_boundary2_precise(analysis, ranges, width)

        layer3 = LayerDetector._analyze_layer3(analysis, ranges, height)
        y2_line = LayerDetector._find_boundary3_precise(layer3, width, height)

        x_coords = np.arange(width, dtype=int)
        y0 = np.clip(np.round(y0_line).astype(int), 0, height - 1)
        y1 = np.clip(np.round(y1_line).astype(int), 0, height - 1)
        y2 = np.clip(np.round(y2_line).astype(int), 0, height - 1)

        # Гарантируем монотонность сверху вниз: y0 ≤ y1 ≤ y2.
        y1 = np.maximum(y1, y0)
        y2 = np.maximum(y2, y1)

        return BoundaryDetectionResult(x=x_coords, y0=y0, y1=y1, y2=y2)

    # ── Шаг 1: Multi-Otsu и сглаженные распределения ────────────────────────

    @staticmethod
    def _analyze_multithreshold_distribution(image_gray: np.ndarray) -> dict:
        image_uint8 = util.img_as_ubyte(np.clip(image_gray, 0.0, 1.0))
        thresholds = filters.threshold_multiotsu(image_uint8, classes=3)
        quantized = np.digitize(image_uint8, bins=thresholds)

        masks = [quantized == i for i in range(3)]
        height, width = image_uint8.shape
        distributions = [np.sum(mask, axis=1) / width for mask in masks]
        smooth_distributions = [
            gaussian_filter1d(dist, sigma=SIKE_DISTRIBUTION_SIGMA) for dist in distributions
        ]

        return {
            "quantized_image": quantized,
            "smooth_distributions": smooth_distributions,
            "image_uint8": image_uint8,
            "image_gray": image_gray,
        }

    # ── Шаг 2: грубые диапазоны границ ──────────────────────────────────────

    @staticmethod
    def _find_boundary_ranges(analysis: dict, height: int) -> dict:
        smooth_dists = analysis["smooth_distributions"]

        black_smooth = smooth_dists[0]
        white_smooth = smooth_dists[2]

        grad_black = np.gradient(black_smooth)
        grad_white = np.gradient(white_smooth)

        # ── Граница 1: спад чёрных ─────────────────────────────────────────
        black_peak = int(np.argmax(black_smooth))
        if black_peak < len(grad_black):
            min_grad_black = np.min(grad_black[black_peak:])
        else:
            min_grad_black = 0.0
        threshold_black = SIKE_GRAD_THRESHOLD_FRAC * min_grad_black
        steep_fall = np.where(grad_black[black_peak:] < threshold_black)[0]
        b1_start = black_peak + int(steep_fall[0]) if len(steep_fall) > 0 else black_peak

        search_region = black_smooth[b1_start:]
        local_mins, _ = find_peaks(-search_region)
        if len(local_mins) > 0:
            b1_end = int(b1_start + local_mins[0])
        else:
            after_start = grad_black[b1_start:]
            zero_cross = np.where(after_start >= 0)[0]
            b1_end = int(b1_start + zero_cross[0]) if len(zero_cross) > 0 else min(b1_start + 50, height - 1)

        # ── Граница 2: рост белых ─────────────────────────────────────────
        max_grad_white = np.max(grad_white)
        threshold_white = SIKE_GRAD_THRESHOLD_FRAC * max_grad_white
        steep_rise = np.where(grad_white > threshold_white)[0]
        b2_start = int(steep_rise[0]) if len(steep_rise) > 0 else int(np.argmax(grad_white))

        search_region_w = white_smooth[b2_start:]
        local_maxs, _ = find_peaks(search_region_w)
        if len(local_maxs) > 0:
            b2_end = int(b2_start + local_maxs[0])
        else:
            after_start_w = grad_white[b2_start:]
            zero_cross_w = np.where(after_start_w <= 0)[0]
            b2_end = int(b2_start + zero_cross_w[0]) if len(zero_cross_w) > 0 else min(b2_start + 50, height - 1)

        # ── Ruptures: граница 1 (1 точка на участке) ──────────────────────
        seg1 = black_smooth[b1_start:b1_end].reshape(-1, 1)
        if len(seg1) > 2:
            bkp1_local = rpt.Binseg(model="l2").fit(seg1).predict(
                n_bkps=SIKE_RUPTURES_BOUNDARY1_NBKPS
            )[0]
        else:
            bkp1_local = max(1, len(seg1) // 2)
        bkp1 = b1_start + int(bkp1_local)

        # ── Ruptures: граница 2 (берём первые 2 break-points) ─────────────
        algo_white = rpt.Binseg(model="l2").fit(white_smooth.reshape(-1, 1))
        bkps_white = algo_white.predict(n_bkps=SIKE_RUPTURES_BOUNDARY2_NBKPS)[:-1]
        bkp2 = int(bkps_white[0])
        bkp2b = int(bkps_white[1])

        # ── Уточнение границы 1: левый край — уровень 99% ─────────────────
        b1_left = b1_start
        for i in range(bkp1, 0, -1):
            if black_smooth[i] >= SIKE_BOUNDARY1_LEVEL_THRESHOLD:
                b1_left = i
                break

        right_region_black = black_smooth[bkp1:]
        local_mins_right_b, _ = find_peaks(-right_region_black)
        b1_right = bkp1 + int(local_mins_right_b[0]) if len(local_mins_right_b) > 0 else b1_end

        # ── Уточнение диапазона по bkp2 ───────────────────────────────────
        search_left = max(0, bkp2 - SIKE_BOUNDARY2_LEFT_SEARCH_RANGE)
        max_grad_in_rise = np.max(np.abs(grad_white[search_left:bkp2 + 1]))
        flat_threshold = SIKE_BOUNDARY2_FLAT_RATIO * max_grad_in_rise if max_grad_in_rise > 0 else 1e-6
        b2_left = search_left
        for i in range(bkp2, search_left, -1):
            if abs(grad_white[i]) < flat_threshold:
                b2_left = i
                break

        local_maxs_right_w, _ = find_peaks(white_smooth[bkp2:])
        b2_right = bkp2 + int(local_maxs_right_w[0]) if len(local_maxs_right_w) > 0 else min(bkp2 + 100, height - 1)

        # ── Уточнение диапазона по bkp2b ──────────────────────────────────
        local_mins_left_wb, _ = find_peaks(-white_smooth[:bkp2b])
        b2b_left = int(local_mins_left_wb[-1]) if len(local_mins_left_wb) > 0 else bkp2
        b2b_right = height - 1

        return {
            "b1_left": b1_left,
            "b1_right": b1_right,
            "b2_left": b2_left,
            "b2_right": b2_right,
            "b2b_left": b2b_left,
            "b2b_right": b2b_right,
            "bkp1": bkp1,
            "bkp2": bkp2,
            "bkp2b": bkp2b,
        }

    # ── Шаг 3: точная граница 1 (верхние серые пиксели) ─────────────────────

    @staticmethod
    def _find_boundary1_precise(analysis: dict, ranges: dict, width: int) -> np.ndarray:
        quantized = analysis["quantized_image"]
        b1_left = ranges["b1_left"]
        b1_right = ranges["b1_right"]

        raw_line = np.zeros(width, dtype=float)
        for x in range(width):
            segment = quantized[b1_left:b1_right + 1, x]
            grey_indices = np.where(segment == 1)[0]
            if len(grey_indices) > 0:
                raw_line[x] = b1_left + grey_indices[0]
            else:
                raw_line[x] = b1_right

        baseline = median_filter(raw_line, size=SIKE_PRECISE1_MEDIAN_WINDOW)
        fixed_line = np.where(
            raw_line - baseline > SIKE_PRECISE1_DROP_THRESHOLD, baseline, raw_line
        )
        smooth_line = gaussian_filter1d(fixed_line, sigma=SIKE_PRECISE1_SMOOTH_SIGMA)
        smooth_line = np.clip(smooth_line, b1_left, b1_right)
        return smooth_line

    # ── Шаг 4: точная граница 2 (верхние белые пиксели) ─────────────────────

    @staticmethod
    def _find_boundary2_precise(analysis: dict, ranges: dict, width: int) -> np.ndarray:
        quantized = analysis["quantized_image"]
        b2b_left = ranges["b2_left"]
        b2b_right = ranges["b2_right"]

        raw_line = np.zeros(width, dtype=float)
        for x in range(width):
            segment = quantized[b2b_left:b2b_right + 1, x]
            white_indices = np.where(segment == 2)[0]
            if len(white_indices) > 0:
                raw_line[x] = b2b_left + white_indices[0]
            else:
                raw_line[x] = b2b_right

        baseline = median_filter(raw_line, size=SIKE_PRECISE2_MEDIAN_WINDOW)
        fixed_line = np.where(
            raw_line - baseline > SIKE_PRECISE2_DROP_THRESHOLD, baseline, raw_line
        )
        smooth_line = gaussian_filter1d(fixed_line, sigma=SIKE_PRECISE2_SMOOTH_SIGMA)
        smooth_line = np.clip(smooth_line, b2b_left, b2b_right)
        return smooth_line

    # ── Шаг 5: маска слоя 3 (Multi-Otsu 4 класса) ───────────────────────────

    @staticmethod
    def _analyze_layer3(analysis: dict, ranges: dict, height: int) -> dict:
        image_uint8 = analysis["image_uint8"]
        b2b_left = ranges["b2b_left"]
        b2b_right = height - 1

        roi_region_uint8 = image_uint8[b2b_left:b2b_right + 1, :]
        roi_region_uint8 = median_filter(roi_region_uint8, size=SIKE_LAYER3_MEDIAN_SIZE)

        thresholds3 = filters.threshold_multiotsu(roi_region_uint8, classes=SIKE_LAYER3_N_CLASSES)
        quantized3 = np.digitize(roi_region_uint8, bins=thresholds3)

        # классы: 0 = тёмные, 1 = серые, 2 = средние, 3 = светлые
        cleaned = quantized3.copy()
        cleaned[quantized3 == 1] = 0
        cleaned[quantized3 == 2] = 1
        cleaned[quantized3 == 3] = 1

        labeled = measure.label(cleaned, connectivity=2)
        props = measure.regionprops(labeled)
        if props:
            areas = [prop.area for prop in props]
            max_area = max(areas)
        else:
            max_area = 0

        if max_area > 0:
            cleaned = morphology.remove_small_objects(labeled, min_size=max_area)
        else:
            cleaned = labeled

        return {
            "cleaned": cleaned,
            "b2b_left": b2b_left,
            "b2b_right": b2b_right,
        }

    # ── Шаг 6: точная граница 3 (верх плотной маски) ────────────────────────

    @staticmethod
    def _find_boundary3_precise(layer3: dict, width: int, height: int) -> np.ndarray:
        cleaned = layer3["cleaned"]
        b2b_left = layer3["b2b_left"]
        b2b_right = layer3["b2b_right"]

        raw_line = np.full(width, np.nan, dtype=float)
        for x in range(width):
            whites = np.where(cleaned[:, x] > 0)[0]
            if len(whites) > 0:
                raw_line[x] = b2b_left + whites[0]

        valid = ~np.isnan(raw_line)
        if np.any(valid):
            raw_line = np.interp(
                np.arange(width), np.where(valid)[0], raw_line[valid]
            )
        else:
            raw_line[:] = b2b_right

        smooth_line = gaussian_filter1d(raw_line, sigma=SIKE_PRECISE3_SMOOTH_SIGMA)
        smooth_line = np.minimum(smooth_line, raw_line)

        # Срезание вертикальных отростков (резких скачков вверх + соответствующего вниз).
        fixed_line = smooth_line.copy()
        jump_th = SIKE_PRECISE3_JUMP_THRESHOLD
        max_w = SIKE_PRECISE3_MAX_SPIKE_WIDTH
        i = 1
        while i < width - 1:
            dy = smooth_line[i] - smooth_line[i - 1]
            if dy < -jump_th:
                start_idx = i - 1
                end_idx = -1
                for j in range(i, min(i + max_w, width)):
                    if smooth_line[j] - smooth_line[j - 1] > jump_th:
                        end_idx = j
                        break
                if end_idx != -1:
                    x_seg = np.arange(start_idx, end_idx + 1)
                    fixed_line[start_idx:end_idx + 1] = np.linspace(
                        smooth_line[start_idx],
                        smooth_line[end_idx],
                        len(x_seg),
                    )
                    i = end_idx + 1
                else:
                    i += 1
            else:
                i += 1

        smooth_line = gaussian_filter1d(fixed_line, sigma=SIKE_PRECISE3_FINAL_SMOOTH_SIGMA)
        smooth_line = np.clip(smooth_line, b2b_left, b2b_right)
        return smooth_line

    # ── Утилиты ─────────────────────────────────────────────────────────────

    @staticmethod
    def _to_float_gray(image: np.ndarray) -> np.ndarray:
        if image.dtype.kind in {"u", "i"}:
            img = image.astype(np.float64)
            max_val = np.iinfo(image.dtype).max
            if max_val > 0:
                img /= max_val
            return img

        img = image.astype(np.float64)
        if img.max() > 1.0:
            img /= 255.0
        return img
