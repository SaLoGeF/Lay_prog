"""
Результат анализа одного слоя изображения.
Чистая структура данных — никакой логики, только хранение.
"""

from dataclasses import dataclass, field
import numpy as np


@dataclass
class LayerResult:
    name: str                           # "Коллекторный катодный слой" и т.д.
    widths: np.ndarray                  # массив толщин по каждому столбцу (мкм)
    x_top: np.ndarray                   # координаты x верхней границы
    y_top: np.ndarray                   # координаты y верхней границы
    x_bottom: np.ndarray                # координаты x нижней границы
    y_bottom: np.ndarray                # координаты y нижней границы
    porosity: float = 0.0               # пористость слоя [0..1]
    extra: dict = field(default_factory=dict)  # доп. метрики (доля серых/белых)

    # ── Вычисляемые свойства ──────────────────────────────────────────────────

    @property
    def mean_width(self) -> float:
        return float(np.mean(self.widths)) if len(self.widths) else 0.0

    @property
    def min_width(self) -> float:
        return float(np.min(self.widths)) if len(self.widths) else 0.0

    @property
    def max_width(self) -> float:
        return float(np.max(self.widths)) if len(self.widths) else 0.0

    @property
    def std_width(self) -> float:
        return float(np.std(self.widths)) if len(self.widths) else 0.0

    def summary(self) -> str:
        return (
            f"{self.name}\n"
            f"  Среднее: {self.mean_width:.2f} мкм\n"
            f"  Мин:     {self.min_width:.2f} мкм\n"
            f"  Макс:    {self.max_width:.2f} мкм\n"
            f"  σ:       {self.std_width:.2f} мкм\n"
            f"  Пористость: {self.porosity:.3f}\n"
        )