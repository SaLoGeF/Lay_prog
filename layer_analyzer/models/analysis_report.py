"""
Полный отчёт по одному изображению.
Содержит результаты всех слоёв и метаданные.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from .layer_result import LayerResult


@dataclass
class AnalysisReport:
    image_path: Path                            # путь к исходному изображению
    scale_um_per_px: float                      # мкм / пиксель
    layers: list[LayerResult] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    error: str | None = None                    # если анализ завершился с ошибкой
    preview_image: np.ndarray | None = None     # обрезанное изображение для предпросмотра
    gallery_images: dict[str, np.ndarray] = field(default_factory=dict)
    gallery_series: dict[str, tuple[np.ndarray, np.ndarray]] = field(default_factory=dict)
    tpb: object | None = None                   # TpbResult (анализ ТФГ в слое 2)

    @property
    def success(self) -> bool:
        return self.error is None and len(self.layers) > 0

    @property
    def image_name(self) -> str:
        return self.image_path.stem

    def to_log_text(self) -> str:
        """Текстовый лог с максимально подробной информацией."""
        lines = [
            "=" * 80,
            f"АНАЛИЗ ИЗОБРАЖЕНИЯ: {self.image_name}",
            "=" * 80,
            "",
            "▸ ИНФОРМАЦИЯ ОБ ИЗОБРАЖЕНИИ",
            f"  Путь: {self.image_path}",
            f"  Временная метка: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"  Масштаб: {self.scale_um_per_px:.6f} мкм/пиксель",
        ]
        
        if self.preview_image is not None:
            h, w = self.preview_image.shape[:2]
            lines.append(f"  Размер изображения: {w} × {h} пиксель")
        
        if self.error:
            lines.extend([
                "",
                "▸ ОШИБКА АНАЛИЗА",
                f"  {self.error}",
                "",
            ])
        else:
            lines.append(f"  Всего слоёв: {len(self.layers)}")
            lines.append("")
            
            # Детальная информация по каждому слою
            for i, layer in enumerate(self.layers, 1):
                lines.extend([
                    f"▸ СЛОЙ {i}: {layer.name}",
                    f"  Измерения:",
                    f"    Количество точек: {len(layer.widths)}",
                    f"    Средняя толщина: {layer.mean_width:.2f} мкм",
                    f"    Минимальная: {layer.min_width:.2f} мкм",
                    f"    Максимальная: {layer.max_width:.2f} мкм",
                    f"    Стд. отклонение: {layer.std_width:.2f} мкм",
                ])
                
                # Квартили
                if len(layer.widths) > 0:
                    q1, median, q3 = np.percentile(layer.widths, [25, 50, 75])
                    lines.extend([
                        f"    Q1 (25%): {q1:.2f} мкм",
                        f"    Медиана (50%): {median:.2f} мкм",
                        f"    Q3 (75%): {q3:.2f} мкм",
                    ])
                
                lines.extend([
                    f"  Границы слоя:",
                    f"    Верхняя граница: {len(layer.x_top)} точек",
                ])
                
                if len(layer.x_top) > 0:
                    lines.extend([
                        f"      X: [{np.min(layer.x_top):.1f}, {np.max(layer.x_top):.1f}]",
                        f"      Y: [{np.min(layer.y_top):.1f}, {np.max(layer.y_top):.1f}]",
                    ])
                
                lines.append(f"    Нижняя граница: {len(layer.x_bottom)} точек")
                
                if len(layer.x_bottom) > 0:
                    lines.extend([
                        f"      X: [{np.min(layer.x_bottom):.1f}, {np.max(layer.x_bottom):.1f}]",
                        f"      Y: [{np.min(layer.y_bottom):.1f}, {np.max(layer.y_bottom):.1f}]",
                    ])
                
                lines.extend([
                    f"  Физические свойства:",
                    f"    Пористость: {layer.porosity:.3f} ({layer.porosity*100:.1f}%)",
                ])
                
                # Дополнительные метрики
                if layer.extra:
                    lines.append(f"  Дополнительные метрики:")
                    for k, v in layer.extra.items():
                        if isinstance(v, (int, float, str, bool, np.integer, np.floating)):
                            if isinstance(v, (float, np.floating)):
                                lines.append(f"    {k}: {v:.6f}")
                            else:
                                lines.append(f"    {k}: {v}")
                
                lines.append("")
            
            # Информация о ТФГ если есть
            if self.tpb is not None:
                lines.extend([
                    "▸ АНАЛИЗ ТРЁХФАЗНОЙ ГРАНИЦЫ (ТФГ/TPB)",
                    f"  Количество TPB-точек: {self.tpb.tpb_count}",
                ])
                
                if self.tpb.tpb_density_per_um2 is not None:
                    lines.append(f"  Плотность TPB: {self.tpb.tpb_density_per_um2:.2f} точек/мкм²")
                
                if self.tpb.tpb_length_um_per_um2 is not None:
                    lines.append(f"  Длина TPB: {self.tpb.tpb_length_um_per_um2:.2f} мкм/мкм²")
                
                if self.tpb.phase_fractions:
                    lines.append(f"  Фазовые фракции:")
                    for phase_name, fraction in self.tpb.phase_fractions.items():
                        lines.append(f"    {phase_name}: {fraction:.4f}")
                
                lines.extend([
                    f"  Параметры анализа:",
                    f"    Порог градиента: {self.tpb.gradient_threshold:.2f}",
                    f"    Количество маркеров: {self.tpb.n_markers}",
                    f"    Пороги фаз: {self.tpb.phase_thresholds}",
                    "",
                ])
            
            # Информация о галерее
            if self.gallery_images:
                lines.extend([
                    "▸ СГЕНЕРИРОВАННЫЕ ИЗОБРАЖЕНИЯ",
                    f"  Всего изображений: {len(self.gallery_images)}",
                ])
                for img_name in self.gallery_images.keys():
                    lines.append(f"    - {img_name}")
                lines.append("")
            
            if self.gallery_series:
                lines.extend([
                    "▸ ГРАФИКИ И СЕРИИ ДАННЫХ",
                    f"  Всего серий: {len(self.gallery_series)}",
                ])
                for series_name in self.gallery_series.keys():
                    lines.append(f"    - {series_name}")
                lines.append("")
        
        lines.append("=" * 80)
        lines.append("")
        return "\n".join(lines)