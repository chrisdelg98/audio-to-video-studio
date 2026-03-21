"""
BaseEffect — Clase abstracta base para todos los efectos visuales.

Cada efecto hereda de BaseEffect e implementa `build_filter`.
El sistema de efectos es plug-in: basta con crear una nueva clase
que herede de BaseEffect para que sea compatible con el builder.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseEffect(ABC):
    """
    Interfaz base para efectos FFmpeg.

    Un efecto recibe parámetros en el constructor y expone:
    - enabled: si debe aplicarse.
    - build_filter: retorna el fragmento de filtro FFmpeg (string vacío si está deshabilitado).
    - label_in / label_out: etiquetas de stream para encadenar filter_complex.
    """

    def __init__(self, enabled: bool = True, **kwargs: Any) -> None:
        self.enabled = enabled
        self.params: dict[str, Any] = kwargs

    @abstractmethod
    def build_filter(self, label_in: str, label_out: str, duration: float) -> str:
        """
        Construye el fragmento de filtro FFmpeg para este efecto.

        Args:
            label_in:  Etiqueta de entrada del stream de video (e.g. "[v0]").
            label_out: Etiqueta de salida del stream de video (e.g. "[v1]").
            duration:  Duración total del audio/video en segundos.

        Returns:
            Fragmento de filter_complex listo para concatenar, o "" si deshabilitado.
        """

    @property
    def name(self) -> str:
        """Nombre descriptivo del efecto."""
        return self.__class__.__name__

    def __repr__(self) -> str:
        return f"{self.name}(enabled={self.enabled}, params={self.params})"
