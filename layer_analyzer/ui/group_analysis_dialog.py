"""
Диалог сводного анализа группы изображений.

Принимает список AnalysisReport, агрегирует статистику по слоям
(толщины, пористость) и показывает таблицу + объединённые гистограммы.
"""

from __future__ import annotations
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImage, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models.analysis_report import AnalysisReport


class GroupAnalysisDialog(QDialog):
    """Окно сводной статистики по группе изображений."""

    def __init__(
        self,
        reports: list[AnalysisReport],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._reports = [r for r in reports if r.success]
        self._setup_ui()
        self._populate()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setWindowTitle("Сводный анализ группы")
        self.resize(1200, 820)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Заголовок
        self._header = QLabel("Группа изображений")
        self._header.setStyleSheet("font-weight: bold; font-size: 14px;")
        root.addWidget(self._header)

        self._files_label = QLabel("")
        self._files_label.setStyleSheet("color: #4a525e; font-size: 11px;")
        self._files_label.setWordWrap(True)
        root.addWidget(self._files_label)

        # Сводная таблица по слоям
        section_label = QLabel("Сводка по слоям")
        section_label.setStyleSheet("font-weight: bold; font-size: 12px; margin-top: 6px;")
        root.addWidget(section_label)

        self._table = QTableWidget()
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels([
            "Слой",
            "N",
            "⟨толщина⟩, мкм",
            "σ толщины, мкм",
            "min, мкм",
            "max, мкм",
            "⟨пористость⟩",
            "σ пористости",
        ])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        for col in range(1, 8):
            self._table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        self._table.setStyleSheet("font-size: 13px;")
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setMaximumHeight(170)
        root.addWidget(self._table)

        # Карточки с графиками — в скролле
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._charts_holder = QWidget()
        self._charts_layout = QVBoxLayout(self._charts_holder)
        self._charts_layout.setContentsMargins(0, 0, 0, 0)
        self._charts_layout.setSpacing(10)

        scroll.setWidget(self._charts_holder)
        root.addWidget(scroll, stretch=1)

        # Кнопки управления
        bottom = QHBoxLayout()
        bottom.addStretch()

        self._btn_export = QPushButton("💾 Сохранить отчёт…")
        self._btn_export.setMinimumHeight(34)
        self._btn_export.clicked.connect(self._export)
        bottom.addWidget(self._btn_export)

        self._btn_close = QPushButton("Закрыть")
        self._btn_close.setMinimumHeight(34)
        self._btn_close.clicked.connect(self.close)
        bottom.addWidget(self._btn_close)
        root.addLayout(bottom)

    # ── Заполнение ────────────────────────────────────────────────────────────

    def _populate(self) -> None:
        if not self._reports:
            self._header.setText("Сводный анализ — нет данных")
            self._files_label.setText("Среди выбранных файлов нет успешно проанализированных.")
            return

        self._header.setText(f"Сводный анализ — {len(self._reports)} изображений")
        files_txt = ", ".join(r.image_name for r in self._reports)
        self._files_label.setText(files_txt)

        # Собираем по индексу слоя.
        layer_count = max(len(r.layers) for r in self._reports)
        per_layer: list[dict] = []
        for li in range(layer_count):
            entries = []
            pore_series_list: list[tuple] = []  # (edges_px, area_hist_px2, scale)
            for r in self._reports:
                if li >= len(r.layers):
                    continue
                entries.append(r.layers[li])
                series_key = f"pore_area_dist_{li + 1}"
                series = r.gallery_series.get(series_key)
                if series is not None:
                    pore_series_list.append((series[0], series[1], r.scale_um_per_px))
            if not entries:
                continue
            all_widths = np.concatenate(
                [np.asarray(layer.widths, dtype=float) for layer in entries]
            )
            all_widths = all_widths[np.isfinite(all_widths)]
            mean_widths_per_image = np.array(
                [layer.mean_width for layer in entries], dtype=float
            )
            porosities = np.array([layer.porosity for layer in entries], dtype=float)

            per_layer.append({
                "name": entries[0].name,
                "n": len(entries),
                "all_widths": all_widths,
                "per_image_means": mean_widths_per_image,
                "porosities": porosities,
                "pore_series": pore_series_list,
            })

        self._fill_table(per_layer)
        self._fill_charts(per_layer)

    def _fill_table(self, per_layer: list[dict]) -> None:
        self._table.setRowCount(len(per_layer))
        for row, info in enumerate(per_layer):
            widths = info["all_widths"]
            poros = info["porosities"]
            mean_w = float(np.mean(widths)) if widths.size else 0.0
            std_w = float(np.std(widths)) if widths.size else 0.0
            min_w = float(np.min(widths)) if widths.size else 0.0
            max_w = float(np.max(widths)) if widths.size else 0.0
            mean_p = float(np.mean(poros)) if poros.size else 0.0
            std_p = float(np.std(poros)) if poros.size else 0.0

            values = [
                info["name"],
                f"{info['n']}",
                f"{mean_w:.2f}",
                f"{std_w:.2f}",
                f"{min_w:.2f}",
                f"{max_w:.2f}",
                f"{mean_p:.3f}",
                f"{std_p:.3f}",
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if col == 0:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                    )
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, col, item)

        self._table.resizeColumnsToContents()
        self._table.resizeRowsToContents()

    def _fill_charts(self, per_layer: list[dict]) -> None:
        # Очищаем старые виджеты в скроллере.
        while self._charts_layout.count():
            item = self._charts_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.deleteLater()

        for info in per_layer:
            row_w = QWidget()
            row = QHBoxLayout(row_w)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(10)

            # Гистограмма толщин (объединённая)
            hist_label = self._make_chart_card(
                self._build_thickness_hist(info["all_widths"], info["name"])
            )
            row.addWidget(hist_label)

            # Агрегированное распределение размеров пор по площади
            pore_label = self._make_chart_card(
                self._build_aggregated_pore_distribution(info["pore_series"], info["name"])
            )
            row.addWidget(pore_label)

            self._charts_layout.addWidget(row_w)

        self._charts_layout.addStretch()

    @staticmethod
    def _make_chart_card(pixmap: QPixmap) -> QLabel:
        lbl = QLabel()
        lbl.setMinimumSize(560, 360)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            "background: #ffffff; border: 1px solid #cfd6e2; border-radius: 8px; padding: 4px;"
        )
        scaled = pixmap.scaled(
            560,
            360,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        lbl.setPixmap(scaled)
        return lbl

    @staticmethod
    def _build_thickness_hist(widths: np.ndarray, layer_name: str) -> QPixmap:
        fig = Figure(figsize=(6.4, 4.0), dpi=110)
        canvas = FigureCanvasAgg(fig)
        ax = fig.add_subplot(111)
        fig.patch.set_facecolor("#f8f8f8")
        ax.set_facecolor("#f8f8f8")

        widths = widths[np.isfinite(widths)]
        if widths.size > 0:
            bins_count = max(10, min(40, int(np.sqrt(widths.size) * 1.5)))
            ax.hist(
                widths,
                bins=bins_count,
                density=True,
                color="#4285f4",
                edgecolor="black",
                linewidth=0.6,
            )
            ax.axvline(
                float(np.mean(widths)),
                color="#d83b3b",
                linestyle="--",
                linewidth=1.5,
                label=f"среднее = {np.mean(widths):.2f}",
            )
            ax.legend(fontsize=10, loc="upper right")
        else:
            ax.text(0.5, 0.5, "Нет данных", ha="center", va="center", transform=ax.transAxes)

        ax.set_title(f"Распределение толщин (объединённое): {layer_name}", fontsize=11, fontweight="bold")
        ax.set_xlabel("Толщина, мкм", fontsize=10)
        ax.set_ylabel("Плотность вероятности", fontsize=10)
        ax.tick_params(axis="both", labelsize=9)
        ax.grid(True, linestyle="--", linewidth=0.6, alpha=0.5)

        fig.tight_layout()
        canvas.draw()
        return GroupAnalysisDialog._canvas_to_pixmap(canvas)

    @staticmethod
    def _build_aggregated_pore_distribution(
        pore_series_list: list[tuple], layer_name: str
    ) -> QPixmap:
        """Агрегированная гистограмма размеров пор по площади.

        X = диаметр поры, мкм (D = 2 · r · scale).
        Y = суммарная площадь, занимаемая порами с этим диаметром, мкм²
            (просуммировано по всем изображениям группы).
        """
        fig = Figure(figsize=(6.4, 4.0), dpi=110)
        canvas = FigureCanvasAgg(fig)
        ax = fig.add_subplot(111)
        fig.patch.set_facecolor("#f8f8f8")
        ax.set_facecolor("#f8f8f8")

        # Каждое изображение: (edges_px, area_hist_px2, scale)
        # Переводим bin-центры в диаметры (мкм) и веса в мкм², потом
        # перебинируем все точки в общую сетку.
        all_diam_centers: list[np.ndarray] = []
        all_area_um2: list[np.ndarray] = []
        for edges_px, area_hist_px2, scale in pore_series_list:
            edges_px = np.asarray(edges_px, dtype=float)
            area_hist_px2 = np.asarray(area_hist_px2, dtype=float)
            if edges_px.size < 2 or area_hist_px2.size == 0:
                continue
            scale = max(float(scale), 1e-12)
            diam_edges_um = 2.0 * edges_px * scale
            diam_centers = 0.5 * (diam_edges_um[:-1] + diam_edges_um[1:])
            area_um2 = area_hist_px2 * (scale ** 2)
            all_diam_centers.append(diam_centers)
            all_area_um2.append(area_um2)

        if not all_diam_centers:
            ax.text(0.5, 0.5, "Нет данных по порам", ha="center", va="center",
                    transform=ax.transAxes, fontsize=11)
            ax.set_xticks([]); ax.set_yticks([])
            fig.tight_layout(); canvas.draw()
            return GroupAnalysisDialog._canvas_to_pixmap(canvas)

        flat_centers = np.concatenate(all_diam_centers)
        flat_areas = np.concatenate(all_area_um2)

        d_min = max(0.0, float(np.min(flat_centers)))
        d_max = float(np.max(flat_centers))
        if d_max <= d_min:
            d_max = d_min + 1.0

        natural_steps: list[float] = []
        for centers in all_diam_centers:
            if centers.size >= 2:
                natural_steps.append(float(np.median(np.diff(centers))))
        bin_step = max(0.2, min(natural_steps) if natural_steps else 0.5)
        edges_um = np.arange(d_min, d_max + bin_step, bin_step, dtype=float)
        if edges_um.size < 2:
            edges_um = np.array([d_min, d_min + bin_step], dtype=float)

        agg_area, _ = np.histogram(flat_centers, bins=edges_um, weights=flat_areas)
        centers_um = 0.5 * (edges_um[:-1] + edges_um[1:])

        ax.bar(
            centers_um,
            agg_area,
            width=np.diff(edges_um),
            align="center",
            color="#f39c12",
            edgecolor="black",
            linewidth=0.6,
        )

        total_area = float(np.sum(agg_area))
        if total_area > 0:
            mean_diam = float(np.sum(centers_um * agg_area) / total_area)
            ax.axvline(
                mean_diam,
                color="#d83b3b",
                linestyle="--",
                linewidth=1.5,
                label=f"⟨D⟩ по площади = {mean_diam:.2f} мкм",
            )
            ax.legend(fontsize=9, loc="upper right")

        ax.set_title(
            f"Распределение пор по площади (агрегировано): {layer_name}",
            fontsize=11, fontweight="bold",
        )
        ax.set_xlabel("Диаметр поры, мкм", fontsize=10)
        ax.set_ylabel("Суммарная площадь пор, мкм²", fontsize=10)
        ax.tick_params(axis="both", labelsize=9)
        ax.grid(True, linestyle="--", linewidth=0.6, alpha=0.5)

        fig.tight_layout()
        canvas.draw()
        return GroupAnalysisDialog._canvas_to_pixmap(canvas)

    @staticmethod
    def _canvas_to_pixmap(canvas: FigureCanvasAgg) -> QPixmap:
        buf = np.asarray(canvas.buffer_rgba())
        h, w, _ = buf.shape
        rgb = np.ascontiguousarray(buf[:, :, :3])
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(qimg.copy())

    # ── Экспорт ───────────────────────────────────────────────────────────────

    def _export(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Папка для сохранения отчёта группы")
        if not folder:
            return
        out = Path(folder) / "group_analysis"
        out.mkdir(parents=True, exist_ok=True)

        # Текстовый отчёт
        lines = [f"Group analysis: {len(self._reports)} images", ""]
        lines.append("Files:")
        for r in self._reports:
            lines.append(f"  - {r.image_name}")
        lines.append("")

        for row in range(self._table.rowCount()):
            cells = []
            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                cells.append(item.text() if item else "")
            lines.append("\t".join(cells))

        (out / "summary.txt").write_text("\n".join(lines), encoding="utf-8")

        # Сохраняем все картинки графиков
        idx = 0
        for i in range(self._charts_layout.count()):
            row_item = self._charts_layout.itemAt(i)
            row_w = row_item.widget() if row_item else None
            if row_w is None:
                continue
            row_layout = row_w.layout()
            if row_layout is None:
                continue
            for j in range(row_layout.count()):
                w = row_layout.itemAt(j).widget()
                if isinstance(w, QLabel) and w.pixmap() is not None and not w.pixmap().isNull():
                    w.pixmap().save(str(out / f"chart_{idx:02d}.png"), "PNG")
                    idx += 1
