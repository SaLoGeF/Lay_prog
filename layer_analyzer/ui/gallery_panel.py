"""
Центральная панель карточек с изображениями после анализа.
Показывает исходное изображение, границы, поры и распределения.
"""

from __future__ import annotations
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
import numpy as np
import skimage as ski
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QDialog
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QColor
from PyQt6.QtCore import Qt, pyqtSignal, QRect

from models.analysis_report import AnalysisReport


BORDER_COLORS = [
    QColor(255, 80, 80),
    QColor(80, 200, 120),
    QColor(80, 160, 255),
    QColor(255, 200, 60),
]


class LightboxDialog(QDialog):
    """Модальное окно просмотра изображения с затемнённым фоном."""

    def __init__(self, pixmap: QPixmap, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap = pixmap
        self._image_rect = QRect()

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        if parent is not None:
            self.resize(parent.size())
        else:
            self.resize(1200, 800)

    def _fit_rect(self) -> QRect:
        margin = 40
        area = self.rect().adjusted(margin, margin, -margin, -margin)
        if area.width() <= 0 or area.height() <= 0:
            return QRect()

        pw = max(1, self._pixmap.width())
        ph = max(1, self._pixmap.height())
        pr = pw / ph
        ar = area.width() / area.height()

        if pr > ar:
            w = area.width()
            h = int(w / pr)
            x = area.left()
            y = area.top() + (area.height() - h) // 2
        else:
            h = area.height()
            w = int(h * pr)
            x = area.left() + (area.width() - w) // 2
            y = area.top()
        return QRect(x, y, w, h)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 170))

        self._image_rect = self._fit_rect()
        if not self._image_rect.isNull():
            painter.drawPixmap(self._image_rect, self._pixmap)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self._image_rect.contains(event.position().toPoint()):
            self.close()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)


class ImageCard(QFrame):
    """Одна карточка изображения."""

    double_clicked = pyqtSignal(QPixmap)

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: #ffffff; border: 1px solid #cfd6e2; border-radius: 8px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self._title = QLabel(title)
        self._title.setStyleSheet("font-size: 12px; font-weight: bold; color: #2f3742;")
        layout.addWidget(self._title)

        self._thumb = QLabel("Нет данных")
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setMinimumSize(320, 220)
        self._thumb.setStyleSheet("background: #f6f8fc; border: 1px solid #d6dce7; border-radius: 6px; color: #6f7782;")
        layout.addWidget(self._thumb)

    def set_title(self, text: str) -> None:
        self._title.setText(text)

    def set_image(self, pixmap: QPixmap | None) -> None:
        self._pixmap = pixmap
        if pixmap is None or pixmap.isNull():
            self._thumb.setText("Нет данных")
            self._thumb.setPixmap(QPixmap())
            return

        scaled = pixmap.scaled(
            self._thumb.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._thumb.setText("")
        self._thumb.setPixmap(scaled)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._pixmap is not None and not self._pixmap.isNull():
            self.set_image(self._pixmap)

    def mouseDoubleClickEvent(self, _event) -> None:  # noqa: N802
        if self._pixmap is not None and not self._pixmap.isNull():
            self.double_clicked.emit(self._pixmap)


class GalleryPanel(QWidget):
    """Панель карточек результатов для центральной части окна."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Визуализация")
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        root.addWidget(title)

        cards_row = QHBoxLayout()
        cards_row.setContentsMargins(0, 0, 0, 0)
        cards_row.setSpacing(10)

        self._card_original = ImageCard("Исходное изображение")
        self._card_borders = ImageCard("Изображение с границами")

        cards_row.addWidget(self._card_original)
        cards_row.addWidget(self._card_borders)
        root.addLayout(cards_row)

        dist_row = QHBoxLayout()
        dist_row.setContentsMargins(0, 0, 0, 0)
        dist_row.setSpacing(10)

        self._card_dist_1 = ImageCard("Распределение толщины слоя 1")
        self._card_dist_2 = ImageCard("Распределение толщины слоя 2")

        dist_row.addWidget(self._card_dist_1)
        dist_row.addWidget(self._card_dist_2)
        root.addLayout(dist_row)

        pores_row = QHBoxLayout()
        pores_row.setContentsMargins(0, 0, 0, 0)
        pores_row.setSpacing(10)

        self._card_pores_1 = ImageCard("Поры (сферы) в слое 1")
        self._card_pores_2 = ImageCard("Поры (сферы) в слое 2")

        pores_row.addWidget(self._card_pores_1)
        pores_row.addWidget(self._card_pores_2)
        root.addLayout(pores_row)

        pore_dist_row = QHBoxLayout()
        pore_dist_row.setContentsMargins(0, 0, 0, 0)
        pore_dist_row.setSpacing(10)

        self._card_pore_dist_1 = ImageCard("Распределение размеров пор (по площади), слой 1")
        self._card_pore_dist_2 = ImageCard("Распределение размеров пор (по площади), слой 2")

        pore_dist_row.addWidget(self._card_pore_dist_1)
        pore_dist_row.addWidget(self._card_pore_dist_2)
        root.addLayout(pore_dist_row)

        # ── Карточки TPB ───────────────────────────────────────────────
        tpb_row = QHBoxLayout()
        tpb_row.setContentsMargins(0, 0, 0, 0)
        tpb_row.setSpacing(10)

        self._card_tpb_phase = ImageCard("Сегментация фаз (слой 2): pore / ECP / ICP")
        self._card_tpb_overlay = ImageCard("Трёхфазная граница — позиции точек")

        tpb_row.addWidget(self._card_tpb_phase)
        tpb_row.addWidget(self._card_tpb_overlay)
        root.addLayout(tpb_row)

        self._hint = QLabel("Двойной клик по карточке — открыть увеличенное изображение")
        self._hint.setStyleSheet("color: #6f7782; font-size: 11px;")
        root.addWidget(self._hint)

        self._card_original.double_clicked.connect(self._open_lightbox)
        self._card_borders.double_clicked.connect(self._open_lightbox)
        self._card_dist_1.double_clicked.connect(self._open_lightbox)
        self._card_dist_2.double_clicked.connect(self._open_lightbox)
        self._card_pores_1.double_clicked.connect(self._open_lightbox)
        self._card_pores_2.double_clicked.connect(self._open_lightbox)
        self._card_pore_dist_1.double_clicked.connect(self._open_lightbox)
        self._card_pore_dist_2.double_clicked.connect(self._open_lightbox)
        self._card_tpb_phase.double_clicked.connect(self._open_lightbox)
        self._card_tpb_overlay.double_clicked.connect(self._open_lightbox)

    def clear(self) -> None:
        self._card_original.set_image(None)
        self._card_borders.set_image(None)
        self._card_dist_1.set_image(None)
        self._card_dist_2.set_image(None)
        self._card_pores_1.set_image(None)
        self._card_pores_2.set_image(None)
        self._card_pore_dist_1.set_image(None)
        self._card_pore_dist_2.set_image(None)
        self._card_tpb_phase.set_image(None)
        self._card_tpb_overlay.set_image(None)

    def show_images(self, path: Path, report: AnalysisReport) -> None:
        cards = self._build_gallery_pixmaps(path, report)
        self._card_original.set_image(cards["original"])
        self._card_borders.set_image(cards["borders"])
        self._card_dist_1.set_image(cards["thickness_dist_1"])
        self._card_dist_2.set_image(cards["thickness_dist_2"])
        self._card_pores_1.set_image(cards["pores_overlay_1"])
        self._card_pores_2.set_image(cards["pores_overlay_2"])
        self._card_pore_dist_1.set_image(cards["pore_area_dist_1"])
        self._card_pore_dist_2.set_image(cards["pore_area_dist_2"])
        self._card_tpb_phase.set_image(cards.get("tpb_phase"))
        self._card_tpb_overlay.set_image(cards.get("tpb_overlay"))

    def build_export_pixmaps(self, path: Path, report: AnalysisReport) -> dict[str, QPixmap]:
        cards = self._build_gallery_pixmaps(path, report)
        return {k: v for k, v in cards.items() if v is not None and not v.isNull()}

    def _build_gallery_pixmaps(self, path: Path, report: AnalysisReport) -> dict[str, QPixmap | None]:
        original = ski.io.imread(str(path), as_gray=True)
        if original.max() > 0:
            original = original / original.max()

        original_pixmap = self._array_to_pixmap(original)
        cards: dict[str, QPixmap | None] = {
            "original": original_pixmap,
            "borders": None,
            "thickness_dist_1": None,
            "thickness_dist_2": None,
            "pores_overlay_1": None,
            "pores_overlay_2": None,
            "pore_area_dist_1": None,
            "pore_area_dist_2": None,
        }

        if report.preview_image is not None:
            analyzed = report.preview_image
            if analyzed.max() > 0:
                analyzed = analyzed / analyzed.max()
            analyzed_pixmap = self._array_to_pixmap(analyzed)
            if analyzed_pixmap is not None:
                cards["borders"] = self._draw_borders(analyzed_pixmap, analyzed.shape, report)

        if len(report.layers) > 0 and len(report.layers[0].widths) > 0:
            cards["thickness_dist_1"] = self._build_histogram_pixmap(
                report.layers[0].widths,
                f"{report.layers[0].name}",
            )

        if len(report.layers) > 1 and len(report.layers[1].widths) > 0:
            cards["thickness_dist_2"] = self._build_histogram_pixmap(
                report.layers[1].widths,
                f"{report.layers[1].name}",
            )

        overlay_1 = report.gallery_images.get("pores_overlay_1")
        overlay_2 = report.gallery_images.get("pores_overlay_2")
        cards["pores_overlay_1"] = self._array_to_pixmap(overlay_1) if overlay_1 is not None else None
        cards["pores_overlay_2"] = self._array_to_pixmap(overlay_2) if overlay_2 is not None else None

        series_1 = report.gallery_series.get("pore_area_dist_1")
        series_2 = report.gallery_series.get("pore_area_dist_2")
        cards["pore_area_dist_1"] = (
            self._build_area_distribution_pixmap(series_1, "Слой 1", report.scale_um_per_px)
            if series_1 is not None
            else None
        )
        cards["pore_area_dist_2"] = (
            self._build_area_distribution_pixmap(series_2, "Слой 2", report.scale_um_per_px)
            if series_2 is not None
            else None
        )

        # ── TPB ────────────────────────────────────────────────────────
        if report.tpb is not None:
            cards["tpb_phase"] = self._build_tpb_phase_pixmap(report.tpb)
            cards["tpb_overlay"] = self._build_tpb_overlay_pixmap(report.tpb)
        else:
            cards["tpb_phase"] = None
            cards["tpb_overlay"] = None

        return cards

    def _open_lightbox(self, pixmap: QPixmap) -> None:
        dlg = LightboxDialog(pixmap, parent=self.window())
        dlg.exec()

    @staticmethod
    def _array_to_pixmap(img: np.ndarray | None) -> QPixmap | None:
        if img is None:
            return None

        arr = np.asarray(img)
        if arr.ndim == 2:
            if arr.dtype != np.uint8:
                arr = (np.clip(arr, 0, 1) * 255).astype(np.uint8)
            h, w = arr.shape
            qimg = QImage(arr.tobytes(), w, h, w, QImage.Format.Format_Grayscale8)
            return QPixmap.fromImage(qimg)

        if arr.ndim == 3 and arr.shape[2] == 3:
            if arr.dtype != np.uint8:
                arr = (np.clip(arr, 0, 1) * 255).astype(np.uint8)
            h, w, _ = arr.shape
            qimg = QImage(arr.tobytes(), w, h, w * 3, QImage.Format.Format_RGB888)
            return QPixmap.fromImage(qimg)

        return None

    @staticmethod
    def _draw_borders(pixmap: QPixmap, shape: tuple[int, int], report: AnalysisReport) -> QPixmap:
        result = QPixmap(pixmap)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        img_h, img_w = shape
        pw, ph = pixmap.width(), pixmap.height()
        sx, sy = pw / img_w, ph / img_h

        borders: list[tuple[np.ndarray, np.ndarray]] = []
        for layer in report.layers:
            borders.append((layer.x_top, layer.y_top))
        if report.layers:
            borders.append((report.layers[-1].x_bottom, report.layers[-1].y_bottom))

        for i, (xs, ys) in enumerate(borders):
            color = BORDER_COLORS[i % len(BORDER_COLORS)]
            painter.setPen(QPen(color, 7))
            step = max(1, len(xs) // 1000)
            pts = list(zip(xs[::step] * sx, ys[::step] * sy))
            for j in range(1, len(pts)):
                painter.drawLine(
                    int(pts[j - 1][0]), int(pts[j - 1][1]),
                    int(pts[j][0]), int(pts[j][1]),
                )

        painter.end()
        return result

    @staticmethod
    def _build_histogram_pixmap(widths: np.ndarray, title: str) -> QPixmap:
        vals = np.asarray(widths, dtype=float)
        vals = vals[np.isfinite(vals)]
        if vals.size == 0:
            empty = QPixmap(1400, 900)
            empty.fill(QColor(248, 248, 248))
            return empty

        bins_count = max(8, min(30, int(np.sqrt(vals.size) * 1.8)))
        fig = Figure(figsize=(14, 9), dpi=100)
        canvas = FigureCanvasAgg(fig)
        ax = fig.add_subplot(111)

        fig.patch.set_facecolor("#f8f8f8")
        ax.set_facecolor("#f8f8f8")

        ax.hist(vals, bins=bins_count, density=True, color="#4285f4", edgecolor="black", linewidth=0.8)

        ax.set_title(f"Распределение толщины: {title}", fontsize=22, fontweight="bold", pad=18)
        ax.set_xlabel("Толщина, мкм", fontsize=19, labelpad=12)
        ax.set_ylabel("Плотность вероятности, 1/мкм", fontsize=19, labelpad=18)
        ax.tick_params(axis="both", labelsize=14)
        ax.locator_params(axis="x", nbins=7)
        ax.locator_params(axis="y", nbins=7)
        ax.grid(True, linestyle="--", linewidth=0.8, alpha=0.5)

        fig.tight_layout()
        canvas.draw()
        return GalleryPanel._mpl_canvas_to_pixmap(canvas)

    @staticmethod
    def _build_area_distribution_pixmap(
        series: tuple[np.ndarray, np.ndarray],
        layer_label: str,
        scale_um_per_px: float,
    ) -> QPixmap:
        edges, area_hist_px2 = series

        edges = np.asarray(edges, dtype=float)
        area_hist_px2 = np.asarray(area_hist_px2, dtype=float)
        if edges.size < 2 or area_hist_px2.size == 0:
            empty = QPixmap(1400, 900)
            empty.fill(QColor(248, 248, 248))
            return empty

        bins_count = len(area_hist_px2)
        scale = max(float(scale_um_per_px), 1e-12)
        diam_edges_um = 2.0 * edges * scale
        area_hist_um2 = area_hist_px2 * (scale ** 2)
        fig = Figure(figsize=(14, 9), dpi=100)
        canvas = FigureCanvasAgg(fig)
        ax = fig.add_subplot(111)

        fig.patch.set_facecolor("#f8f8f8")
        ax.set_facecolor("#f8f8f8")

        diam_centers_um = 0.5 * (diam_edges_um[:-1] + diam_edges_um[1:])
        widths_um = np.diff(diam_edges_um)
        ax.bar(
            diam_centers_um,
            area_hist_um2,
            width=widths_um,
            align="center",
            color="#f39c12",
            edgecolor="black",
            linewidth=0.8,
        )

        ax.set_title(
            f"Распределение диаметров пор по площади: {layer_label}",
            fontsize=22,
            fontweight="bold",
            pad=18,
        )
        ax.set_xlabel("Диаметр пор, мкм", fontsize=19, labelpad=12)
        ax.set_ylabel("Общая занимаемая площадь, мкм²", fontsize=19, labelpad=18)
        ax.tick_params(axis="both", labelsize=14)
        ax.locator_params(axis="x", nbins=7)
        ax.locator_params(axis="y", nbins=7)
        ax.grid(True, linestyle="--", linewidth=0.8, alpha=0.5)

        fig.tight_layout()
        canvas.draw()
        return GalleryPanel._mpl_canvas_to_pixmap(canvas)

    @staticmethod
    def _mpl_canvas_to_pixmap(canvas: FigureCanvasAgg) -> QPixmap:
        buf = np.asarray(canvas.buffer_rgba())
        h, w, _ = buf.shape
        # Keep a local contiguous RGB copy for stable handoff to QImage.
        rgb = np.ascontiguousarray(buf[:, :, :3])
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(qimg.copy())

    # ── TPB ────────────────────────────────────────────────────────────────

    @staticmethod
    def _tpb_figsize(roi_shape: tuple[int, int]) -> tuple[float, float]:
        """Подбираем figsize так, чтобы фигура соответствовала пропорциям ROI."""
        roi_h, roi_w = roi_shape
        if roi_h <= 0 or roi_w <= 0:
            return (14.0, 6.0)
        fig_w = 14.0
        title_h = 1.4   # запас под заголовок
        fig_h = fig_w * roi_h / roi_w + title_h
        fig_h = max(4.0, min(20.0, fig_h))
        return fig_w, fig_h

    @staticmethod
    def _build_tpb_phase_pixmap(tpb) -> QPixmap:
        """Цветовая карта 3 фаз: pore (тёмно-синий), ECP (оранж), ICP (белый)."""
        phase = tpb.phase  # int8: -1 / 0 / 1 / 2
        h, w = phase.shape
        rgb = np.zeros((h, w, 3), dtype=np.uint8)
        rgb[phase == 0] = (40, 50, 80)
        rgb[phase == 1] = (220, 130, 60)
        rgb[phase == 2] = (240, 240, 240)
        # вне маски — чёрный (по умолчанию)

        fig = Figure(figsize=GalleryPanel._tpb_figsize(phase.shape), dpi=100)
        canvas = FigureCanvasAgg(fig)
        ax = fig.add_subplot(111)
        fig.patch.set_facecolor("#f8f8f8")
        ax.set_facecolor("#f8f8f8")
        ax.imshow(rgb, interpolation="nearest")

        f = tpb.phase_fractions
        ax.set_title(
            f"Сегментация фаз слоя 2 (Auto-Post)\n"
            f"pore={f.get('pore', 0):.3f}   "
            f"ECP={f.get('ecp', 0):.3f}   "
            f"ICP={f.get('icp', 0):.3f}",
            fontsize=18, fontweight="bold", pad=14,
        )
        ax.set_xticks([]); ax.set_yticks([])
        from matplotlib.patches import Patch
        legend = [
            Patch(facecolor=(40 / 255, 50 / 255, 80 / 255), label="pore"),
            Patch(facecolor=(220 / 255, 130 / 255, 60 / 255), label="ECP"),
            Patch(facecolor=(240 / 255, 240 / 255, 240 / 255), edgecolor="black", label="ICP"),
        ]
        ax.legend(handles=legend, loc="upper right", fontsize=14, framealpha=0.85)

        fig.tight_layout()
        canvas.draw()
        return GalleryPanel._mpl_canvas_to_pixmap(canvas)

    @staticmethod
    def _build_tpb_overlay_pixmap(tpb) -> QPixmap:
        """ROI слоя 2 (grayscale) + маркеры на TPB-точках."""
        roi = tpb.roi
        is_tpb = tpb.is_tpb
        ys, xs = np.where(is_tpb)

        fig = Figure(figsize=GalleryPanel._tpb_figsize(roi.shape), dpi=100)
        canvas = FigureCanvasAgg(fig)
        ax = fig.add_subplot(111)
        fig.patch.set_facecolor("#f8f8f8")
        ax.set_facecolor("#f8f8f8")

        ax.imshow(roi, cmap="gray", interpolation="nearest")
        if xs.size > 0:
            ax.scatter(
                xs + 0.5,
                ys + 0.5,
                s=10,
                marker="o",
                c="red",
                edgecolors="black",
                linewidths=0.4,
                alpha=0.95,
            )

        density = tpb.tpb_density_per_um2
        title = f"TPB-точек: {tpb.tpb_count}"
        if density is not None:
            title += f"   ({density:.4f} точек/мкм²)"
        ax.set_title(title, fontsize=18, fontweight="bold", pad=14)
        ax.set_xticks([]); ax.set_yticks([])

        fig.tight_layout()
        canvas.draw()
        return GalleryPanel._mpl_canvas_to_pixmap(canvas)
