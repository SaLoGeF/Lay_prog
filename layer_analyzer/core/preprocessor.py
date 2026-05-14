"""
Предобработка изображения:
  1. Обрезка нижней информационной полосы (метаданные микроскопа).
  2. Гамма-коррекция.

Масштаб (мкм/пиксель) передаётся снаружи — пользователь вводит его
в интерфейсе. Это надёжнее OCR и не требует тяжёлых зависимостей.
"""

from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import skimage as ski

from config import GAMMA_CORRECTION


class Preprocessor:

    def process(
        self,
        image: np.ndarray,
        scale_um_per_px: float,
      auto_crop: bool = True,
      manual_crop_box: tuple[int, int, int, int] | None = None,
    ) -> tuple[np.ndarray, np.ndarray, float]:
        """
        Параметры:
          image           -- float64 grayscale [0..1]
          scale_um_per_px -- масштаб, введённый пользователем (мкм/пиксель)

        Возвращает:
          cropped         -- обрезанное изображение
          gamma_corrected -- гамма-скорректированная версия
          scale           -- тот же масштаб (передаётся дальше в pipeline)
        """
        if auto_crop:
          cropped = self._auto_crop(image)
        else:
          cropped = self._manual_crop(image, manual_crop_box)

        gamma_corrected = ski.exposure.adjust_gamma(cropped, gamma=GAMMA_CORRECTION)
        return cropped, gamma_corrected, scale_um_per_px

    @staticmethod
    def _auto_crop(image: np.ndarray) -> np.ndarray:
        """
        Обрезает нижнюю информационную полосу микроскопа.
        Ищет последние две строки с белым пикселем у правого края.
        Если полоса не найдена -- возвращает изображение без изменений.
        """
        height, width = image.shape
        binary = image > 0.5

        crop_row = 0
        hits = 0
        for h in range(height - 2, 0, -1):
            if binary[h, width - 2]:
                crop_row = h
                hits += 1
            if hits == 2:
                break

        if crop_row > height // 2:
            return image[:crop_row]
        return image

    @staticmethod
    def _manual_crop(
        image: np.ndarray,
        crop_box: tuple[int, int, int, int] | None,
      ) -> np.ndarray:
        if crop_box is None:
          raise ValueError("Не задана область ручной обрезки")

        left, top, right, bottom = crop_box
        height, width = image.shape

        left = int(np.clip(left, 0, width - 1))
        top = int(np.clip(top, 0, height - 1))
        right = int(np.clip(right, left + 1, width))
        bottom = int(np.clip(bottom, top + 1, height))

        cropped = image[top:bottom, left:right]
        if cropped.size == 0:
          raise ValueError("Область обрезки пуста")
        return cropped