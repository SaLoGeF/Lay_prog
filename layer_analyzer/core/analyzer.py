"""
Оркестратор анализа одного изображения.
Соединяет preprocessor → layer_detector → вычисление метрик.
Возвращает AnalysisReport — больше ничего не делает.
"""

from __future__ import annotations
from pathlib import Path
from typing import Callable

import numpy as np
import skimage as ski
from scipy.ndimage import distance_transform_edt

from config import (
    N_CLASSES,
    PORE_MIN_RADIUS,
    PORE_MAX_RADIUS,
    PORE_RADIUS_STEP,
    PORE_DIST_BIN_STEP,
)
from models.analysis_report import AnalysisReport
from models.layer_result import LayerResult
from .image_loader import ImageLoader
from .preprocessor import Preprocessor
from .layer_detector import LayerDetector
from .tpb_analyzer import TpbAnalyzer


class Analyzer:
    """
    Использование:
        analyzer = Analyzer()
        report = analyzer.run(Path("image.tif"), progress_cb=print)
    """

    def __init__(self) -> None:
        self._preprocessor = Preprocessor()
        self._detector = LayerDetector()

    def run(
        self,
        image_path: Path,
        scale_um_per_px: float,
        progress_cb: Callable[[str, int], None] | None = None,
        auto_crop: bool = True,
        manual_crop_box: tuple[int, int, int, int] | None = None,
    ) -> AnalysisReport:
        """
        Параметры:
          image_path       -- путь к изображению
          scale_um_per_px  -- масштаб (мкм/пиксель), введённый пользователем
          progress_cb      -- callback(message, percent) для обновления прогресса
        """
        def progress(msg: str, pct: int) -> None:
            if progress_cb:
                progress_cb(msg, pct)

        report = AnalysisReport(image_path=image_path, scale_um_per_px=scale_um_per_px)

        try:
            progress("Загрузка изображения...", 5)
            img = ImageLoader.load(image_path)

            progress("Предобработка и определение масштаба...", 15)
            img, gamma, scale = self._preprocessor.process(
                img,
                scale_um_per_px,
                auto_crop=auto_crop,
                manual_crop_box=manual_crop_box,
            )
            report.scale_um_per_px = scale
            report.preview_image = img.copy()

            progress("Сегментация слоёв...", 30)
            layers, gallery_images, gallery_series, tpb_result = self._detect_all_layers(img, gamma, scale, progress)
            report.layers = layers
            report.gallery_images = gallery_images
            report.gallery_series = gallery_series
            report.tpb = tpb_result

        except Exception as exc:
            report.error = str(exc)

        return report

    # ── Внутренняя логика ─────────────────────────────────────────────────────

    def _detect_all_layers(
        self,
        img: np.ndarray,
        gamma: np.ndarray,
        scale: float,
        progress: Callable[[str, int], None],
    ) -> tuple[list[LayerResult], dict[str, np.ndarray], dict[str, tuple[np.ndarray, np.ndarray]], object | None]:
        progress("Поиск границ слоёв...", 40)
        boundaries = self._detector.detect_boundaries(img)
        x0, y0 = boundaries.x, boundaries.y0
        x1, y1 = boundaries.x, boundaries.y1
        x2, y2 = boundaries.x, boundaries.y2

        # ── Вычисление толщин и пористости ───────────────────────────────────
        progress("Вычисление метрик...", 80)

        # Глобальный 3-классовый Multi-Otsu на обрезанном изображении.
        # Используется как единое определение «чёрного» (= нижний класс)
        # для обоих слоёв — согласованно для серии изображений.
        thresholds_img = ski.filters.threshold_multiotsu(img, classes=N_CLASSES)

        layer1 = self._build_layer1(img, x0, y0, x1, y1, scale, thresholds_img)
        layer2 = self._build_layer2(img, x1, y1, x2, y2, scale, thresholds_img)

        progress("Анализ пористости слоёв...", 87)

        pore_porosity_1, pore_count_1, overlay_1, series_1 = self._analyze_pores_for_layer(
            img,
            x0,
            y0,
            x1,
            y1,
            color=(255, 70, 70),
            title="Слой 1",
        )
        pore_porosity_2, pore_count_2, overlay_2, series_2 = self._analyze_pores_for_layer(
            img,
            x1,
            y1,
            x2,
            y2,
            color=(70, 255, 120),
            title="Слой 2",
        )

        # Основная пористость = площадь вписанных окружностей / площадь слоя.
        # Это физичнее «черных пикселей по порогу», особенно когда сглаженная
        # верхняя граница слоя 1 захватывает фоновые тёмные пиксели.
        layer1.porosity = round(float(pore_porosity_1), 3)
        layer1.extra["pore_count"] = int(pore_count_1)
        layer2.porosity = round(float(pore_porosity_2), 3)
        layer2.extra["pore_count"] = int(pore_count_2)

        gallery_images = {
            "pores_overlay_1": overlay_1,
            "pores_overlay_2": overlay_2,
        }
        gallery_series = {
            "pore_area_dist_1": series_1,
            "pore_area_dist_2": series_2,
        }

        # ── TPB-анализ слоя 2 (Auto-Post, Kent et al. 2025) ─────────────────
        progress("Анализ трёхфазной границы (TPB)...", 94)
        tpb_result = TpbAnalyzer.analyze(
            img,
            y1,                # верх слоя 2 (= граница 2)
            y2,                # низ слоя 2 (= граница 3)
            scale_um_per_px=scale,
        )
        if tpb_result is not None:
            layer2.extra["tpb_count"] = int(tpb_result.tpb_count)
            if tpb_result.tpb_density_per_um2 is not None:
                layer2.extra["tpb_density_per_um2"] = round(float(tpb_result.tpb_density_per_um2), 4)
            layer2.extra["pore_fraction"] = round(float(tpb_result.phase_fractions["pore"]), 3)
            layer2.extra["ecp_fraction"] = round(float(tpb_result.phase_fractions["ecp"]), 3)
            layer2.extra["icp_fraction"] = round(float(tpb_result.phase_fractions["icp"]), 3)

        progress("Готово", 100)
        return [layer1, layer2], gallery_images, gallery_series, tpb_result

    def _analyze_pores_for_layer(
        self,
        base_image: np.ndarray,
        x_top: np.ndarray,
        y_top: np.ndarray,
        x_bottom: np.ndarray,
        y_bottom: np.ndarray,
        color: tuple[int, int, int],
        title: str,
    ) -> tuple[float, int, np.ndarray, tuple[np.ndarray, np.ndarray]]:
        layer_img = self._mask_outside_discrete_layer_to_white(
            base_image,
            x_top,
            y_top,
            x_bottom,
            y_bottom,
        )
        pores, used_mask = self._iterative_max_inscribed_circles(
            layer_img,
            min_radius=PORE_MIN_RADIUS,
            max_radius=PORE_MAX_RADIUS,
            step=PORE_RADIUS_STEP,
        )

        layer_area = int(np.count_nonzero(layer_img < 0.999))
        pore_porosity = self._calculate_porosity(pores, layer_area)
        overlay = self._draw_pores_on_image(base_image, pores, color=color)
        series = self._pore_area_distribution(pores, bin_step=PORE_DIST_BIN_STEP)
        return pore_porosity, len(pores), overlay, series

    @staticmethod
    def _iterative_max_inscribed_circles(
        gray_image: np.ndarray,
        min_radius: int,
        max_radius: int,
        step: int,
    ) -> tuple[list[tuple[int, int, int]], np.ndarray]:
        h, w = gray_image.shape
        if h == 0 or w == 0:
            return [], np.zeros_like(gray_image, dtype=bool)

        try:
            otsu = ski.filters.threshold_multiotsu(gray_image, classes=3)
            pore_mask = gray_image < otsu[0]
        except Exception:
            return [], np.zeros_like(gray_image, dtype=bool)

        max_radius = int(max(1, min(max_radius, np.max(distance_transform_edt(pore_mask)))))
        min_radius = int(max(1, min(min_radius, max_radius)))
        step = int(max(1, step))

        distance_map = distance_transform_edt(pore_mask)
        used_mask = np.zeros_like(pore_mask, dtype=bool)
        yy, xx = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
        pores: list[tuple[int, int, int]] = []

        for radius in range(max_radius, min_radius - 1, -step):
            candidates = np.argwhere((distance_map >= radius) & (~used_mask))

            for y, x in candidates:
                if used_mask[y, x]:
                    continue

                y_min = max(0, y - radius)
                y_max = min(h, y + radius + 1)
                x_min = max(0, x - radius)
                x_max = min(w, x + radius + 1)

                y_slice = slice(y_min, y_max)
                x_slice = slice(x_min, x_max)

                sub_yy = yy[y_slice, x_slice]
                sub_xx = xx[y_slice, x_slice]
                circle_mask = (sub_yy - y) ** 2 + (sub_xx - x) ** 2 <= radius ** 2

                sub_used = used_mask[y_slice, x_slice]
                if np.any(sub_used[circle_mask]):
                    continue

                used_mask[y_slice, x_slice][circle_mask] = True
                pores.append((int(x), int(y), int(radius)))

        return pores, used_mask

    @staticmethod
    def _mask_outside_discrete_layer_to_white(
        gray_image: np.ndarray,
        x_top: np.ndarray,
        y_top: np.ndarray,
        x_bottom: np.ndarray,
        y_bottom: np.ndarray,
    ) -> np.ndarray:
        height, width = gray_image.shape
        output = np.ones_like(gray_image, dtype=float)

        x_top = np.asarray(x_top, dtype=int)
        y_top = np.asarray(y_top, dtype=int)
        x_bottom = np.asarray(x_bottom, dtype=int)
        y_bottom = np.asarray(y_bottom, dtype=int)

        for xt, yt, xb, yb in zip(x_top, y_top, x_bottom, y_bottom):
            x = int(xt)
            if x < 0 or x >= width:
                continue

            y_start = max(0, min(int(yt), int(yb)))
            y_end = min(height - 1, max(int(yt), int(yb)))
            if y_end >= y_start:
                output[y_start:y_end + 1, x] = gray_image[y_start:y_end + 1, x]

        return output

    @staticmethod
    def _calculate_porosity(pores: list[tuple[int, int, int]], total_area: int) -> float:
        if total_area <= 0:
            return 0.0
        total_pore_area = sum(np.pi * (r ** 2) for _, _, r in pores)
        return float(total_pore_area / total_area)

    @staticmethod
    def _draw_pores_on_image(
        base_image: np.ndarray,
        pores: list[tuple[int, int, int]],
        color: tuple[int, int, int],
    ) -> np.ndarray:
        img = np.asarray(base_image)
        if img.ndim == 2:
            img_u8 = (np.clip(img, 0, 1) * 255).astype(np.uint8)
            overlay = np.stack([img_u8, img_u8, img_u8], axis=-1)
        else:
            overlay = (np.clip(img, 0, 1) * 255).astype(np.uint8).copy()

        h, w = overlay.shape[:2]

        # Cache ring pixel offsets by radius to avoid repeated mask recomputation.
        ring_cache: dict[int, tuple[np.ndarray, np.ndarray]] = {}

        for x, y, r in pores:
            x = int(x)
            y = int(y)
            r = int(r)
            if r <= 0:
                continue

            if r not in ring_cache:
                tol = max(1, r)
                rg = np.arange(-r, r + 1, dtype=np.int32)
                dy, dx = np.meshgrid(rg, rg, indexing="ij")
                dist2 = dy * dy + dx * dx
                ring = np.abs(dist2 - r * r) <= tol
                ring_cache[r] = (dy[ring], dx[ring])

            dy_ring, dx_ring = ring_cache[r]
            ys = y + dy_ring
            xs = x + dx_ring
            inside = (ys >= 0) & (ys < h) & (xs >= 0) & (xs < w)
            if np.any(inside):
                overlay[ys[inside], xs[inside]] = color

        return overlay

    @staticmethod
    def _pore_area_distribution(
        pores: list[tuple[int, int, int]],
        bin_step: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        if len(pores) == 0:
            return np.array([0.0, 1.0], dtype=float), np.array([0.0], dtype=float)

        radii = np.array([r for _, _, r in pores], dtype=float)
        areas = np.pi * radii ** 2
        min_r = float(np.min(radii))
        max_r = float(np.max(radii))
        step = max(0.1, float(bin_step))
        edges = np.arange(min_r, max_r + step, step, dtype=float)
        if edges.size < 2:
            edges = np.array([min_r, max_r + step], dtype=float)

        area_hist_px2, edges = np.histogram(radii, bins=edges, weights=areas)
        return edges, area_hist_px2.astype(float)

    # ── Построение результатов слоёв ──────────────────────────────────────────

    def _build_layer1(self, img, x1, y1, x2, y2, scale, thresholds_global) -> LayerResult:
        """
        Слой 1 (коллекторный катодный): серая матрица + чёрные поры.
        Пористость = #{пиксели маски слоя со значением < t_black} / #{всего в маске}.
        t_black — нижний порог 3-классового Multi-Otsu, посчитанный на ВСЁМ
        обрезанном изображении (общий для слоёв и серии — для согласованности).
        """
        widths = (y2 - y1) * scale
        mask = self._make_mask(img.shape, y1, y2)
        pixels_in_layer = img[mask]
        n_total = int(pixels_in_layer.size)

        t_black = float(thresholds_global[0]) if len(thresholds_global) > 0 else 0.0
        n_black = int(np.count_nonzero(pixels_in_layer < t_black)) if n_total > 0 else 0
        porosity = n_black / max(n_total, 1)

        return LayerResult(
            name="Коллекторный катодный слой",
            widths=widths,
            x_top=x1, y_top=y1,
            x_bottom=x2, y_bottom=y2,
            porosity=round(porosity, 3),
            extra={
                "n_pixels_in_layer": n_total,
                "n_black_pixels": n_black,
                "black_threshold": round(t_black, 4),
            },
        )

    def _build_layer2(self, img, x2, y2, x3, y3, scale, thresholds_global) -> LayerResult:
        """
        Слой 2 (функциональный композитный): 3 фазы — поры/ECP/ICP.
        Пористость = #{пиксели маски слоя со значением < t_black} / #{всего в маске}.
        Дополнительно — gray/white fractions для контроля.
        Пороги t_black, t_white — то же 3-классовое Multi-Otsu по всему изображению.
        """
        widths = (y3 - y2) * scale
        mask = self._make_mask(img.shape, y2, y3)
        pixels_in_layer = img[mask]
        n_total = int(pixels_in_layer.size)

        t_black = float(thresholds_global[0]) if len(thresholds_global) > 0 else 0.0
        t_white = float(thresholds_global[1]) if len(thresholds_global) > 1 else 1.0

        n_black = n_gray = n_white = 0
        if n_total > 0:
            n_black = int(np.count_nonzero(pixels_in_layer < t_black))
            n_gray = int(
                np.count_nonzero((pixels_in_layer >= t_black) & (pixels_in_layer < t_white))
            )
            n_white = int(np.count_nonzero(pixels_in_layer >= t_white))

        denom = max(n_total, 1)
        porosity = n_black / denom
        return LayerResult(
            name="Функциональный композитный катодный слой",
            widths=widths,
            x_top=x2, y_top=y2,
            x_bottom=x3, y_bottom=y3,
            porosity=round(porosity, 3),
            extra={
                "n_pixels_in_layer": n_total,
                "n_black_pixels": n_black,
                "gray_fraction": round(n_gray / denom, 3),
                "white_fraction": round(n_white / denom, 3),
                "black_threshold": round(t_black, 4),
                "white_threshold": round(t_white, 4),
            },
        )

    # ── Вспомогательные ───────────────────────────────────────────────────────

    @staticmethod
    def _make_mask(
        shape: tuple[int, int],
        y_top: np.ndarray,
        y_bottom: np.ndarray | int,
    ) -> np.ndarray:
        mask = np.zeros(shape[:2], dtype=bool)
        width = shape[1]
        if isinstance(y_bottom, int):
            y_bottom = np.full(width, y_bottom)
        for x in range(width):
            lo = int(np.clip(y_top[x], 0, shape[0]))
            hi = int(np.clip(y_bottom[x], 0, shape[0]))
            if lo < hi:
                mask[lo:hi, x] = True
        return mask