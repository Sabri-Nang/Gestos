"""Configuración TOML y validación antes de abrir cámara o escritorio."""

from dataclasses import dataclass, field, fields
import math
from pathlib import Path
import tomllib

from .gestures import GestureConfig

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "gesto.toml"


@dataclass(frozen=True)
class CameraConfig:
    index: int = 0
    mirror: bool = True
    confidence: float = 0.6

    def __post_init__(self):
        if self.index < 0 or not 0 < self.confidence <= 1:
            raise ValueError("Índice de cámara o confianza inválidos.")


@dataclass(frozen=True)
class PresentationConfig:
    countdown: int = 5
    fist_hold_ms: int = 1000
    release_ms: int = 300

    def __post_init__(self):
        if self.countdown < 1 or min(self.fist_hold_ms, self.release_ms) <= 0:
            raise ValueError("Los tiempos de presentación deben ser positivos.")


@dataclass(frozen=True)
class KeyConfig:
    next: str = "right"
    previous: str = "left"

    def __post_init__(self):
        if not self.next or not self.previous or self.next == self.previous:
            raise ValueError("Las teclas deben ser distintas y no vacías.")


@dataclass(frozen=True)
class Settings:
    camera: CameraConfig = field(default_factory=CameraConfig)
    gestures: GestureConfig = field(default_factory=GestureConfig)
    presentation: PresentationConfig = field(default_factory=PresentationConfig)
    keys: KeyConfig = field(default_factory=KeyConfig)


def load_settings(path: Path = DEFAULT_CONFIG) -> Settings:
    with path.open("rb") as source:
        data = tomllib.load(source)
    sections = {"camera": CameraConfig, "gestures": GestureConfig,
                "presentation": PresentationConfig, "keys": KeyConfig}
    unknown = data.keys() - sections.keys()
    if unknown:
        raise ValueError(f"Secciones desconocidas: {', '.join(sorted(unknown))}")
    values = {}
    for section, cls in sections.items():
        content = data.get(section, {})
        if not isinstance(content, dict):
            raise ValueError(f"{section} debe ser una tabla TOML.")
        expected = {item.name: item.type for item in fields(cls)}
        for name, value in content.items():
            if name not in expected:
                raise ValueError(f"Opción desconocida: {section}.{name}")
            kind = expected[name]
            valid = (type(value) in (int, float) and math.isfinite(value)
                     if kind is float else type(value) is kind)
            if not valid:
                raise ValueError(f"Tipo inválido para {section}.{name}")
        values[section] = cls(**content)
    return Settings(**values)
