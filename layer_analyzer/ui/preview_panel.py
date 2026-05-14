"""
Панель предпросмотра изображения.
Показывает исходное изображение, при наличии отчёта — рисует границы слоёв.
"""

from __future__ import annotations
from pathlib import Path

import numpy as np
import skimage as ski
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QColor
from PyQt6.QtCore import Qt, QSize, QRectF, QPointF, pyqtSignal

from config import PREVIEW_MAX_SIZE
from models.analysis_report import AnalysisReport


# Цвета границ слоёв
BORDER_COLORS = [
    QColor(255, 80, 80),    # красный — граница 1
    QColor(80, 200, 120),   # зелёный — граница 2
    QColor(80, 160, 255),   # синий   — граница 3
    QColor(255, 200, 60),   # жёлтый  — граница 4 (нижняя)
]


class CropPreviewLabel(QLabel):
    """QLabel с интерактивной рамкой ручной обрезки."""

    crop_changed = pyqtSignal(object)  # tuple[left, top, right, bottom]

    _HANDLE_SIZE = 10.0
    _MIN_RECT_SIZE = 20.0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(QSize(*PREVIEW_MAX_SIZE))
        self.setStyleSheet(
            "border: 1px solid #c5ccd8; background: #f5f7fb; border-radius: 4px;"
        )

        self._pixmap: QPixmap | None = None
        self._img_w = 0
        self._img_h = 0
        self._draw_rect = QRectF()

        self._manual_crop_enabled = False
        self._crop_rect_img = QRectF()

        self._drag_mode = "none"
        self._last_pos = QPointF()

        self.setMouseTracking(True)

    def set_preview(
        self,
        pixmap: QPixmap,
        image_shape: tuple[int, int],
        manual_crop_enabled: bool,
        crop_box: tuple[int, int, int, int] | None,
    ) -> None:
        self._pixmap = pixmap
        self._img_h, self._img_w = image_shape
        self._manual_crop_enabled = manual_crop_enabled

        if crop_box is not None:
            left, top, right, bottom = crop_box
            self._crop_rect_img = QRectF(
                float(left),
                float(top),
                float(max(1, right - left)),
                float(max(1, bottom - top)),
            )
        elif self._img_w > 0 and self._img_h > 0:
            margin_x = self._img_w * 0.05
            margin_y = self._img_h * 0.05
            self._crop_rect_img = QRectF(
                margin_x,
                margin_y,
                self._img_w - margin_x * 2,
                self._img_h - margin_y * 2,
            )

        self.update()

    def current_crop_box(self) -> tuple[int, int, int, int] | None:
        if self._img_w <= 0 or self._img_h <= 0:
            return None
        r = self._crop_rect_img.normalized()
        left = max(0, min(self._img_w - 2, int(round(r.left()))))
        top = max(0, min(self._img_h - 2, int(round(r.top()))))
        right = max(left + 1, min(self._img_w, int(round(r.right())) + 1))
        bottom = max(top + 1, min(self._img_h, int(round(r.bottom())) + 1))
        return (left, top, right, bottom)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(245, 247, 251))

        if self._pixmap is None:
            super().paintEvent(_event)
            return

        self._draw_rect = self._fit_rect(self._pixmap.size().width(), self._pixmap.size().height())
        painter.drawPixmap(self._draw_rect.toRect(), self._pixmap)

        if self._manual_crop_enabled and self._img_w > 0 and self._img_h > 0:
            crop_w = self._img_to_widget(self._crop_rect_img)
            self._draw_crop_overlay(painter, crop_w)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self._manual_crop_enabled or event.button() != Qt.MouseButton.LeftButton:
            return
        if not self._draw_rect.contains(event.position()):
            return
        self._last_pos = event.position()
        self._drag_mode = self._hit_test(event.position())
        if self._drag_mode == "none" and self._img_to_widget(self._crop_rect_img).contains(event.position()):
            self._drag_mode = "move"

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not self._manual_crop_enabled:
            return

        if self._drag_mode == "none":
            self._update_cursor(event.position())
            return

        dx = event.position().x() - self._last_pos.x()
        dy = event.position().y() - self._last_pos.y()
        self._last_pos = event.position()

        scale_x = self._img_w / max(self._draw_rect.width(), 1.0)
        scale_y = self._img_h / max(self._draw_rect.height(), 1.0)
        ddx = dx * scale_x
        ddy = dy * scale_y

        r = QRectF(self._crop_rect_img)
        if self._drag_mode == "move":
            r.translate(ddx, ddy)
            if r.left() < 0:
                r.translate(-r.left(), 0)
            if r.top() < 0:
                r.translate(0, -r.top())
            if r.right() > self._img_w:
                r.translate(self._img_w - r.right(), 0)
            if r.bottom() > self._img_h:
                r.translate(0, self._img_h - r.bottom())
        else:
            if "left" in self._drag_mode:
                r.setLeft(max(0.0, min(r.right() - self._MIN_RECT_SIZE, r.left() + ddx)))
            if "right" in self._drag_mode:
                r.setRight(min(float(self._img_w), max(r.left() + self._MIN_RECT_SIZE, r.right() + ddx)))
            if "top" in self._drag_mode:
                r.setTop(max(0.0, min(r.bottom() - self._MIN_RECT_SIZE, r.top() + ddy)))
            if "bottom" in self._drag_mode:
                r.setBottom(min(float(self._img_h), max(r.top() + self._MIN_RECT_SIZE, r.bottom() + ddy)))

        self._crop_rect_img = r.normalized()
        self.crop_changed.emit(self.current_crop_box())
        self.update()

    def mouseReleaseEvent(self, _event) -> None:  # noqa: N802
        self._drag_mode = "none"

    def _draw_crop_overlay(self, painter: QPainter, crop_w: QRectF) -> None:
        painter.setOpacity(0.45)
        overlay = Qt.GlobalColor.black
        top_h = max(0.0, crop_w.top() - self._draw_rect.top())
        bottom_h = max(0.0, self._draw_rect.bottom() - crop_w.bottom())

        if top_h > 0:
            painter.fillRect(QRectF(self._draw_rect.left(), self._draw_rect.top(), self._draw_rect.width(), top_h), overlay)
        if bottom_h > 0:
            painter.fillRect(QRectF(self._draw_rect.left(), crop_w.bottom(), self._draw_rect.width(), bottom_h), overlay)

        left_w = max(0.0, crop_w.left() - self._draw_rect.left())
        right_w = max(0.0, self._draw_rect.right() - crop_w.right())
        if left_w > 0:
            painter.fillRect(QRectF(self._draw_rect.left(), crop_w.top(), left_w, crop_w.height()), overlay)
        if right_w > 0:
            painter.fillRect(QRectF(crop_w.right(), crop_w.top(), right_w, crop_w.height()), overlay)

        painter.setOpacity(1.0)

        painter.setPen(QPen(Qt.GlobalColor.white, 2))
        painter.drawRect(crop_w)
        painter.setBrush(Qt.GlobalColor.white)
        for rect in self._handles(crop_w).values():
            painter.drawRect(rect)

    def _fit_rect(self, src_w: int, src_h: int) -> QRectF:
        area = self.rect().adjusted(8, 8, -8, -8)
        if area.width() <= 0 or area.height() <= 0 or src_h <= 0:
            return QRectF()
        src_ratio = src_w / src_h
        area_ratio = area.width() / area.height()
        if src_ratio > area_ratio:
            w = area.width()
            h = w / src_ratio
            x = area.left()
            y = area.top() + (area.height() - h) / 2
        else:
            h = area.height()
            w = h * src_ratio
            x = area.left() + (area.width() - w) / 2
            y = area.top()
        return QRectF(x, y, w, h)

    def _img_to_widget(self, rect_img: QRectF) -> QRectF:
        sx = self._draw_rect.width() / max(self._img_w, 1)
        sy = self._draw_rect.height() / max(self._img_h, 1)
        return QRectF(
            self._draw_rect.left() + rect_img.left() * sx,
            self._draw_rect.top() + rect_img.top() * sy,
            rect_img.width() * sx,
            rect_img.height() * sy,
        )

    def _handles(self, crop_widget: QRectF) -> dict[str, QRectF]:
        hs = self._HANDLE_SIZE
        cx, cy = crop_widget.center().x(), crop_widget.center().y()

        def sq(x: float, y: float) -> QRectF:
            return QRectF(x - hs / 2, y - hs / 2, hs, hs)

        return {
            "top_left": sq(crop_widget.left(), crop_widget.top()),
            "top": sq(cx, crop_widget.top()),
            "top_right": sq(crop_widget.right(), crop_widget.top()),
            "right": sq(crop_widget.right(), cy),
            "bottom_right": sq(crop_widget.right(), crop_widget.bottom()),
            "bottom": sq(cx, crop_widget.bottom()),
            "bottom_left": sq(crop_widget.left(), crop_widget.bottom()),
            "left": sq(crop_widget.left(), cy),
        }

    def _hit_test(self, pos: QPointF) -> str:
        crop_widget = self._img_to_widget(self._crop_rect_img)
        for name, rect in self._handles(crop_widget).items():
            if rect.contains(pos):
                return name
        if crop_widget.contains(pos):
            return "move"
        return "none"

    def _update_cursor(self, pos: QPointF) -> None:
        mode = self._hit_test(pos)
        if mode in {"top_left", "bottom_right"}:
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif mode in {"top_right", "bottom_left"}:
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif mode in {"left", "right"}:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif mode in {"top", "bottom"}:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif mode == "move":
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)


class PreviewPanel(QWidget):

    crop_changed = pyqtSignal(object)  # tuple[left, top, right, bottom]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._report: AnalysisReport | None = None
        self._current_path: Path | None = None
        self._manual_crop_enabled = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Предпросмотр")
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        self._label = CropPreviewLabel()
        self._label.crop_changed.connect(self.crop_changed.emit)
        layout.addWidget(self._label)

        self._info_label = QLabel("")
        self._info_label.setStyleSheet("color: #6f7782; font-size: 11px;")
        self._info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._info_label)

    # ── Публичный API ─────────────────────────────────────────────────────────

    def set_manual_crop_enabled(self, enabled: bool) -> None:
        self._manual_crop_enabled = enabled

    def show_file(
        self,
        path: Path,
        report: AnalysisReport | None = None,
        manual_crop_box: tuple[int, int, int, int] | None = None,
    ) -> None:
        """Отобразить изображение. Если report передан — нарисовать границы."""
        self._report = report
        self._current_path = path
        try:
            if report and report.success and report.preview_image is not None:
                img = report.preview_image
            else:
                img = ski.io.imread(str(path), as_gray=True)
            if img.max() > 0:
                img = img / img.max()
            pixmap = self._to_pixmap(img)
            if report and report.success:
                pixmap = self._draw_borders(pixmap, img.shape, report)
            self._label.set_preview(
                pixmap,
                img.shape,
                manual_crop_enabled=self._manual_crop_enabled,
                crop_box=manual_crop_box,
            )
            scale_txt = f"{report.scale_um_per_px:.4f} мкм/пкс" if report else ""
            self._info_label.setText(
                f"{path.name}  |  {img.shape[1]}×{img.shape[0]} px  {scale_txt}"
            )
        except Exception as exc:
            self._label.clear()
            self._label.setText(f"Ошибка предпросмотра:\n{exc}")

    def clear(self) -> None:
        self._label.clear()
        self._info_label.clear()
        self._current_path = None

    # ── Внутренние ────────────────────────────────────────────────────────────

    @staticmethod
    def _to_pixmap(img: np.ndarray) -> QPixmap:
        uint8 = (img * 255).astype(np.uint8)
        h, w = uint8.shape
        qimg = QImage(uint8.tobytes(), w, h, w, QImage.Format.Format_Grayscale8)
        return QPixmap.fromImage(qimg)

    @staticmethod
    def _draw_borders(
        pixmap: QPixmap,
        shape: tuple[int, int],
        report: AnalysisReport,
    ) -> QPixmap:
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
            pen = QPen(color, 7)
            painter.setPen(pen)
            step = max(1, len(xs) // 1000)  # не рисуем все 4096 точек
            pts = list(zip(xs[::step] * sx, ys[::step] * sy))
            for j in range(1, len(pts)):
                painter.drawLine(
                    int(pts[j - 1][0]), int(pts[j - 1][1]),
                    int(pts[j][0]),     int(pts[j][1]),
                )

        painter.end()
        return result