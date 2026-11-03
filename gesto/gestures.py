"""Detección temporal de barridos; independiente de cámara, MediaPipe y teclado."""

from dataclasses import dataclass
from enum import StrEnum
import math


class State(StrEnum):
    NO_HAND = "SIN MANO"
    STABILIZING = "ESTABILIZANDO"
    READY = "LISTO"
    TRACKING = "MOVIMIENTO"
    COOLDOWN = "ESPERA"
    PAUSED = "PAUSADO"
    OCCLUDED = "RECUPERANDO MANO"


@dataclass(frozen=True)
class GestureConfig:
    distance: float = 0.20
    stable_ms: int = 300
    cooldown_ms: int = 800
    min_duration_ms: int = 150
    max_duration_ms: int = 700
    smoothing_ms: int = 80
    tolerance: float = 0.035
    horizontal_ratio: float = 1.5
    max_gap_ms: int = 250
    dropout_ms: int = 120
    recovery_distance: float = 0.12
    hand_switch_ms: int = 120

    def __post_init__(self):
        if not 0 < self.tolerance < self.distance <= 1:
            raise ValueError("La distancia debe ser mayor a la tolerancia y menor o igual a 1.")
        if not 0 < self.min_duration_ms < self.max_duration_ms:
            raise ValueError("Los tiempos mínimo y máximo del gesto deben ser positivos y crecientes.")
        if min(self.stable_ms, self.smoothing_ms, self.max_gap_ms) <= 0 or self.cooldown_ms < 0:
            raise ValueError("Los tiempos de estabilización, suavizado y muestreo deben ser positivos.")
        if not math.isfinite(self.horizontal_ratio) or self.horizontal_ratio <= 1:
            raise ValueError("El movimiento horizontal debe dominar al vertical.")
        if not 0 <= self.dropout_ms <= self.max_gap_ms or not 0 < self.recovery_distance <= 1:
            raise ValueError("La recuperación debe ser breve y su distancia estar entre 0 y 1.")
        if not 0 < self.hand_switch_ms <= self.max_gap_ms:
            raise ValueError("La confirmación del cambio de mano debe caber dentro del intervalo de muestreo.")


@dataclass(frozen=True)
class GestureEvent:
    action: str
    timestamp_ms: int
    dx: float
    dy: float
    duration_ms: int


def hand_sample(result, *, mirror: bool):
    """Centro de palma en coordenadas espejo, también si la vista no se espeja."""
    if not result.hand_landmarks:
        return None, None
    hand = result.hand_landmarks[0]
    palm = [hand[index] for index in (0, 5, 9, 13, 17)]
    x = sum(point.x for point in palm) / len(palm)
    y = sum(point.y for point in palm) / len(palm)
    identity = result.handedness[0][0].category_name if result.handedness else None
    return (x if mirror else 1 - x, y), identity


class GestureDetector:
    def __init__(self, config: GestureConfig | None = None):
        self.config = config or GestureConfig()
        self.state = State.NO_HAND
        self._last_timestamp = None
        self._hand_id = None
        self._smooth = None
        self._anchor = None
        self._anchor_time = None
        self._cooldown_until = 0
        self._last_seen = None
        self._last_position = None
        self._resume_state = None
        self.reason = "Mostrá una mano y mantenela quieta."
        self.motion = None
        self._candidate_id = self._candidate_since = None

    def _clear(self):
        self._smooth = self._anchor = self._anchor_time = self._hand_id = None
        self._last_seen = self._last_position = self._resume_state = None
        self.motion = None
        self._candidate_id = self._candidate_since = None

    def set_paused(self, paused: bool):
        self._clear()
        self._cooldown_until = 0
        self.state = State.PAUSED if paused else State.NO_HAND
        self.reason = "Pausa manual." if paused else "Mantené la mano quieta para rearmar."

    def _stabilize(self, timestamp, point):
        self.state = State.STABILIZING
        self._anchor, self._anchor_time = point, timestamp
        self.motion = None

    def update(self, timestamp_ms: int, position, hand_id=None) -> GestureEvent | None:
        previous_time = self._last_timestamp
        if previous_time is not None and timestamp_ms <= previous_time:
            raise ValueError("Los timestamps deben ser estrictamente crecientes.")
        self._last_timestamp = timestamp_ms
        self.reason = ""
        if self.state == State.PAUSED:
            return None
        if position is None:
            if self._last_seen is not None and timestamp_ms - self._last_seen <= self.config.dropout_ms:
                if self.state != State.OCCLUDED:
                    self._resume_state = self.state
                    self.state = State.OCCLUDED
                    self.reason = "Pérdida breve: esperando recuperar la mano cerca."
                return None
            if self.state != State.NO_HAND:
                self.reason = "Detección perdida: se descartó la trayectoria."
            self._clear()
            self.state = State.NO_HAND
            return None
        if not all(math.isfinite(p) and 0 <= p <= 1 for p in position):
            self._clear()
            self.state = State.NO_HAND
            self.reason = f"Palma fuera de imagen o coordenadas inválidas: x={position[0]:.3f}, y={position[1]:.3f}."
            return None

        config = self.config
        gap = self._last_seen is not None and timestamp_ms - self._last_seen > config.max_gap_ms
        if gap:
            self._clear()
            self.state = State.NO_HAND
            self.reason = "Intervalo entre muestras demasiado largo; estabilizá de nuevo."
        elif self._smooth is not None and hand_id != self._hand_id:
            # La clasificación izquierda/derecha puede oscilar al girar la palma.
            # Ignorar muestras dudosas solo si siguen cerca de la última palma;
            # un cambio sostenido o una reaparición lejana exige rearmar.
            close = math.dist(position, self._last_position) <= min(
                config.recovery_distance, config.distance * 0.6)
            if close:
                if self._candidate_id != hand_id or self._candidate_since is None:
                    self._candidate_id, self._candidate_since = hand_id, timestamp_ms
                    self.reason = "Clasificación de mano inestable: esperando confirmación."
                if timestamp_ms - self._candidate_since < config.hand_switch_ms:
                    return None
            self._clear()
            self.state = State.NO_HAND
            self.reason = "Cambio de mano confirmado o palma lejana; estabilizá de nuevo."
        else:
            self._candidate_id = self._candidate_since = None
        if self.state == State.OCCLUDED:
            if (timestamp_ms - self._last_seen <= config.dropout_ms
                    and hand_id == self._hand_id
                    and math.dist(position, self._last_position) <= min(
                        config.recovery_distance, config.distance * 0.6)):
                self.state = self._resume_state
                self.reason = "Mano recuperada cerca; continúa el seguimiento."
                if self.state == State.STABILIZING:
                    self._anchor, self._anchor_time = position, timestamp_ms
            else:
                self._clear()
                self.reason = "No se pudo confirmar continuidad; estabilizá de nuevo."
        self._hand_id = hand_id
        last_seen = self._last_seen
        self._last_seen, self._last_position = timestamp_ms, position
        if self._smooth is None:
            self._smooth = position
            self._stabilize(timestamp_ms, position)
            if not self.reason:
                self.reason = "Mano adquirida; mantenela quieta para rearmar."
            return None

        alpha = 1 - math.exp(-(timestamp_ms - last_seen) / config.smoothing_ms)
        self._smooth = tuple(a + alpha * (b - a) for a, b in zip(self._smooth, position))
        if timestamp_ms < self._cooldown_until:
            self.state = State.COOLDOWN
            self._anchor = self._anchor_time = None
            return None
        if self.state in (State.NO_HAND, State.COOLDOWN):
            self._stabilize(timestamp_ms, position)
            return None
        if self.state == State.STABILIZING:
            # La estabilidad se evalúa sin suavizar, para no esconder un retorno.
            if math.dist(self._anchor, position) > config.tolerance:
                self._stabilize(timestamp_ms, position)
            elif timestamp_ms - self._anchor_time >= config.stable_ms:
                self.state = State.READY
                self._anchor, self._anchor_time = self._smooth, timestamp_ms
                self.reason = "Lista para un barrido."
            return None

        dx, dy = (value - origin for value, origin in zip(self._smooth, self._anchor))
        self.motion = (dx, dy, timestamp_ms - self._anchor_time)
        if self.state == State.TRACKING and math.hypot(dx, dy) <= config.tolerance:
            self.state = State.READY
            self._anchor, self._anchor_time = self._smooth, timestamp_ms
            self.reason = "Movimiento pequeño cancelado; lista otra vez."
            return None
        if self.state == State.READY:
            if math.hypot(dx, dy) <= config.tolerance:
                self._anchor_time = timestamp_ms
                return None
            self.state = State.TRACKING
        duration = timestamp_ms - self._anchor_time
        if duration > config.max_duration_ms or abs(dy) >= config.distance:
            self.reason = (f"Barrido vencido: dx={dx:.3f}, dy={dy:.3f}, duración={duration} ms."
                           if duration > config.max_duration_ms else
                           f"Movimiento demasiado vertical: dx={dx:.3f}, dy={dy:.3f}.")
            self._stabilize(timestamp_ms, position)
            return None
        if abs(dx) >= config.distance and duration < config.min_duration_ms:
            self.reason = f"Movimiento demasiado rápido: {duration} ms."
            self._stabilize(timestamp_ms, position)
            return None
        if (duration >= config.min_duration_ms and abs(dx) >= config.distance
                and abs(dx) >= config.horizontal_ratio * abs(dy)):
            event = GestureEvent("next" if dx < 0 else "previous", timestamp_ms, dx, dy, duration)
            self.state = State.COOLDOWN
            self._cooldown_until = timestamp_ms + config.cooldown_ms
            self._anchor = self._anchor_time = None
            return event
        return None
