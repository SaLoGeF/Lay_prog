"""
Загрузка и валидация изображений.
Не занимается обработкой — только проверяет файл и читает его в float64.
"""

from pathlib import Path
import numpy as np
import skimage as ski

from config import SUPPORTED_EXTENSIONS


class ImageLoader:

    @staticmethod
    def _to_grayscale(img: np.ndarray) -> np.ndarray:
        """
        Приводит входное изображение любой канальности к 2D grayscale.
        Для RGB/RGBA использует skimage-конвертеры, для остальных случаев
        усредняет все канальные оси после (H, W).
        """
        if img.ndim == 2:
            return img

        if img.ndim < 2:
            raise ValueError(f"Неожиданная размерность изображения: {img.ndim}D")

        # Поддержка channel-first формата (C, H, W), если C похоже на число каналов.
        if img.ndim == 3 and img.shape[0] <= 16 and img.shape[-1] > 16:
            img = np.moveaxis(img, 0, -1)

        if img.ndim == 3 and img.shape[-1] in (3, 4):
            if img.shape[-1] == 4:
                img = ski.color.rgba2rgb(img)
            return ski.color.rgb2gray(img)

        if img.ndim == 3 and img.shape[-1] == 1:
            return img[..., 0]

        # Общий случай: изображение с произвольным числом каналов/измерений.
        channel_axes = tuple(range(2, img.ndim))
        if not channel_axes:
            raise ValueError(f"Неожиданная размерность изображения: {img.ndim}D")
        return np.mean(img, axis=channel_axes)

    @staticmethod
    def is_supported(path: Path) -> bool:
        return path.suffix.lower() in SUPPORTED_EXTENSIONS

    @staticmethod
    def validate(path: Path) -> None:
        """Бросает ValueError с понятным сообщением если файл нельзя открыть."""
        if not path.exists():
            raise ValueError(f"Файл не найден: {path}")
        if not path.is_file():
            raise ValueError(f"Это не файл: {path}")
        if not ImageLoader.is_supported(path):
            raise ValueError(
                f"Формат не поддерживается: {path.suffix!r}. "
                f"Допустимы: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )

    @staticmethod
    def load(path: Path) -> np.ndarray:
        """
        Читает изображение и возвращает float64 grayscale [0..1].
        Raises ValueError при ошибке чтения.
        """
        ImageLoader.validate(path)
        try:
            img = ski.io.imread(str(path))
        except Exception as exc:
            raise ValueError(f"Не удалось прочитать файл {path.name}: {exc}") from exc

        img = ImageLoader._to_grayscale(img)

        img = ski.util.img_as_float64(img)

        # нормализация на случай если max < 1
        max_val = img.max()
        if max_val > 0:
            img = img / max_val

        return img