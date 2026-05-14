"""
Анализ трёхфазной границы (TPB) в слое между границами 2 и 3.

Методика — Automated Post-Watershed Phase-ID (Auto-Post):
  Kent W.F., Epting W.K., Abernathy H.W., Salvador P.A.
  "Automated phase segmentation with quantifiable sensitivities of three-phase
   microstructures of solid oxide cell electrodes"
  Materials Characterization 226 (2025) 115201
  https://doi.org/10.1016/j.matchar.2025.115201

Шаги:
  1. ROI-маска формы слоя по границам precise2 и precise3.
  2. Sobel-градиент, нормализованный в [0, 1].
  3. Поиск оптимального порога градиента (максимум числа маркеров).
  4. Watershed-сегментация на градиенте.
  5. Marker-average greyscale: каждому региону — среднее серое исходных
     маркер-пикселей.
  6. Multi-Otsu (3 класса) на marker-average → 2 порога фаз.
  7. Phase-ID: 0=pore, 1=ECP, 2=ICP.
  8. TPB-точки: 2×2-окна, в которых встречаются все 3 фазы.
  9. Плотность TPB на единицу площади (точек/мкм²).
"""

from __future__ import annotations
from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.ndimage import mean as ndi_mean
from scipy.signal import find_peaks
from skimage.filters import sobel, threshold_multiotsu
from skimage.measure import label as ski_label
from skimage.segmentation import watershed

from config import (
    TPB_GRAD_SEARCH_MAX_FALLBACK,
    TPB_GRAD_SEARCH_MAX_LIMIT,
    TPB_GRAD_SEARCH_MIN,
    TPB_GRAD_SEARCH_STEPS,
    TPB_GRADIENT_HIST_SIGMA,
    TPB_GRADIENT_PEAK_HEIGHT,
    TPB_PHASE_OTSU_CLASSES,
)


@dataclass
class TpbResult:
    roi: np.ndarray                 # 2D float, ROI слоя 2 в [0..1]
    mask: np.ndarray                # bool 2D, форма слоя в ROI
    phase: np.ndarray               # int8 2D: -1 вне маски, 0/1/2 = pore/ECP/ICP
    is_tpb: np.ndarray              # bool 2D (h-1, w-1) — позиции TPB-точек
    y_offset: int                   # смещение ROI от верха исходного изображения
    tpb_count: int = 0
    tpb_density_per_um2: float | None = None
    tpb_length_um_per_um2: float | None = None
    gradient_threshold: float = 0.0
    n_markers: int = 0
    phase_thresholds: tuple[float, float] = (0.0, 0.0)
    phase_fractions: dict = field(default_factory=dict)


class TpbAnalyzer:

    @staticmethod
    def analyze(
        image_gray: np.ndarray,
        y_top_per_x: np.ndarray,
        y_bottom_per_x: np.ndarray,
        scale_um_per_px: float | None = None,
    ) -> TpbResult | None:
        """
        Параметры:
          image_gray       -- 2D float [0..1] (то же изображение, что подавалось в детектор)
          y_top_per_x      -- y-координата верхней границы (precise2) для каждого x
          y_bottom_per_x   -- y-координата нижней границы (precise3) для каждого x
          scale_um_per_px  -- масштаб (мкм/пкс); None → плотность не вычисляется

        Возвращает TpbResult или None при невозможности анализа.
        """
        height_full, width = image_gray.shape
        y_top = np.round(np.asarray(y_top_per_x)).astype(int)
        y_bot = np.round(np.asarray(y_bottom_per_x)).astype(int)
        if y_top.size != width or y_bot.size != width:
            return None

        # 1. Прямоугольная ROI + маска формы слоя ─────────────────────────
        y_min = max(0, int(np.min(y_top)))
        y_max = min(height_full, int(np.max(y_bot)) + 1)
        if y_max - y_min < 16:
            return None

        roi = image_gray[y_min:y_max, :].astype(float).copy()
        if roi.max() > 1.0:
            roi = roi / roi.max()
        h_roi, w_roi = roi.shape

        mask = np.zeros((h_roi, w_roi), dtype=bool)
        for x in range(w_roi):
            top = max(0, int(y_top[x]) - y_min)
            bot = min(h_roi, int(y_bot[x]) - y_min)
            if bot > top:
                mask[top:bot, x] = True

        if int(mask.sum()) < 1024:
            return None

        # 2. Sobel-градиент, нормализованный ──────────────────────────────
        grad = sobel(roi)
        g_max = float(grad.max()) if grad.size else 0.0
        grad_norm = grad / g_max if g_max > 0 else grad

        # 3. Оптимальный порог градиента (максимум маркеров) ─────────────
        grad_search_max = TpbAnalyzer._find_grad_search_max(grad_norm[mask])
        thresholds = np.linspace(
            grad_search_max / TPB_GRAD_SEARCH_STEPS,
            grad_search_max,
            TPB_GRAD_SEARCH_STEPS,
        )
        n_markers_arr = np.zeros_like(thresholds, dtype=int)
        for i, t in enumerate(thresholds):
            below = (grad_norm < t) & mask
            lbl = ski_label(below, connectivity=2)
            n_markers_arr[i] = int(lbl.max())

        best_idx = int(np.argmax(n_markers_arr))
        best_thresh = float(thresholds[best_idx])
        n_markers_best = int(n_markers_arr[best_idx])
        if n_markers_best == 0:
            return None

        # 4. Watershed на градиенте ─────────────────────────────────────
        below_best = (grad_norm < best_thresh) & mask
        markers = ski_label(below_best, connectivity=2)
        regions = watershed(grad_norm, markers=markers, mask=mask)

        # 5. Marker-average greyscale ──────────────────────────────────
        n_labels = int(markers.max()) + 1
        region_means = ndi_mean(roi, labels=markers, index=np.arange(n_labels))
        region_means = np.nan_to_num(region_means, nan=0.0)
        region_avg = np.where(regions > 0, region_means[regions], 0.0)

        # 6. Multi-Otsu на marker-average → пороги фаз ─────────────────
        avg_in_mask = region_avg[mask]
        avg_in_mask = avg_in_mask[(avg_in_mask > 0.0) & (avg_in_mask < 1.0)]
        if avg_in_mask.size < 100:
            return None
        avg_uint8 = (np.clip(avg_in_mask, 0, 1) * 255).astype(np.uint8)
        try:
            ths = threshold_multiotsu(avg_uint8, classes=TPB_PHASE_OTSU_CLASSES)
        except Exception:
            return None
        th1, th2 = float(ths[0]) / 255.0, float(ths[1]) / 255.0

        # 7. Phase-ID ───────────────────────────────────────────────────
        phase = np.digitize(region_avg, bins=[th1, th2]).astype(np.int8)
        phase_masked = np.where(mask, phase, -1).astype(np.int8)

        n_total = int(mask.sum())
        f_pore = int((phase_masked == 0).sum()) / n_total
        f_ecp = int((phase_masked == 1).sum()) / n_total
        f_icp = int((phase_masked == 2).sum()) / n_total

        # 8. TPB-точки: 2×2-окна, содержащие все 3 фазы ────────────────
        p = phase_masked
        p00 = p[:-1, :-1]; p01 = p[:-1, 1:]
        p10 = p[1:, :-1]; p11 = p[1:, 1:]
        valid = (p00 >= 0) & (p01 >= 0) & (p10 >= 0) & (p11 >= 0)
        has_pore = (p00 == 0) | (p01 == 0) | (p10 == 0) | (p11 == 0)
        has_ecp = (p00 == 1) | (p01 == 1) | (p10 == 1) | (p11 == 1)
        has_icp = (p00 == 2) | (p01 == 2) | (p10 == 2) | (p11 == 2)
        is_tpb = valid & has_pore & has_ecp & has_icp
        n_tpb = int(is_tpb.sum())

        # 9. Плотность TPB ─────────────────────────────────────────────
        density = None
        length_per_area = None
        if scale_um_per_px is not None and scale_um_per_px > 0:
            area_um2 = n_total * (scale_um_per_px ** 2)
            density = n_tpb / area_um2
            length_per_area = (n_tpb * scale_um_per_px) / area_um2

        return TpbResult(
            roi=roi,
            mask=mask,
            phase=phase_masked,
            is_tpb=is_tpb,
            y_offset=y_min,
            tpb_count=n_tpb,
            tpb_density_per_um2=density,
            tpb_length_um_per_um2=length_per_area,
            gradient_threshold=best_thresh,
            n_markers=n_markers_best,
            phase_thresholds=(th1, th2),
            phase_fractions={"pore": f_pore, "ecp": f_ecp, "icp": f_icp},
        )

    # ── Утилиты ─────────────────────────────────────────────────────

    @staticmethod
    def _find_grad_search_max(grad_values: np.ndarray) -> float:
        """Верхний предел поиска порога градиента — позиция 2-го пика гистограммы."""
        if grad_values.size == 0:
            return TPB_GRAD_SEARCH_MAX_FALLBACK
        hist_g, edges_g = np.histogram(grad_values, bins=256, range=(0.0, 1.0))
        hist_g_smooth = gaussian_filter1d(hist_g.astype(float), sigma=TPB_GRADIENT_HIST_SIGMA)
        peaks_g, _ = find_peaks(
            hist_g_smooth, height=hist_g_smooth.max() * TPB_GRADIENT_PEAK_HEIGHT
        )
        if len(peaks_g) >= 2:
            grad_search_max = float(edges_g[peaks_g[1]])
        else:
            grad_search_max = TPB_GRAD_SEARCH_MAX_FALLBACK
        return float(np.clip(grad_search_max, TPB_GRAD_SEARCH_MIN, TPB_GRAD_SEARCH_MAX_LIMIT))
