"""
Панель результатов анализа.
Показывает таблицу с метриками по каждому слою.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QLabel,
    QHeaderView, QTextEdit,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from models.analysis_report import AnalysisReport


class ResultsPanel(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Результаты")
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        # Вкладка: сводная таблица
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ["Слой", "Среднее, мкм", "Мин, мкм", "Макс, мкм", "σ, мкм", "Пористость"]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        for col in range(1, 6):
            self._table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        self._table.setStyleSheet("font-size: 14px;")
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._tabs.addTab(self._table, "Таблица")

        # Вкладка: текстовый лог
        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setFont(__import__('PyQt6.QtGui', fromlist=['QFont']).QFont("Courier New", 10))
        self._log_view.setStyleSheet("font-size: 14px;")
        self._tabs.addTab(self._log_view, "Лог")

    # ── Публичный API ─────────────────────────────────────────────────────────

    def show_report(self, report: AnalysisReport) -> None:
        self._fill_table(report)
        self._log_view.setPlainText(report.to_log_text())

    def show_error(self, message: str) -> None:
        self._table.setRowCount(0)
        self._log_view.setPlainText(f"Ошибка:\n{message}")
        self._tabs.setCurrentIndex(1)

    def clear(self) -> None:
        self._table.setRowCount(0)
        self._log_view.clear()

    # ── Внутренние ────────────────────────────────────────────────────────────

    def _fill_table(self, report: AnalysisReport) -> None:
        self._table.setRowCount(len(report.layers))

        row_colors = [
            QColor(60, 30, 30),
            QColor(30, 50, 35),
            QColor(30, 40, 65),
        ]

        for row, layer in enumerate(report.layers):
            values = [
                layer.name,
                f"{layer.mean_width:.2f}",
                f"{layer.min_width:.2f}",
                f"{layer.max_width:.2f}",
                f"{layer.std_width:.2f}",
                f"{layer.porosity:.3f}",
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter
                    if col > 0 else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
                self._table.setItem(row, col, item)

            self._table.resizeColumnsToContents()
        self._table.resizeRowsToContents()