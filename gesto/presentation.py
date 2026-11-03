"""Control de presentación con pausa por puño sostenido y activación diferida."""

import math

from .config import PresentationConfig
from .gestures import GestureDetector, State, hand_sample


def fist_sample(result) -> bool | None:
    """Heurística geométrica: cuatro puntas plegadas hacia la muñeca, sin el pulgar."""
    if not result.hand_landmarks:
        return None
    # Usar puntos 3D en metros cuando estén disponibles; permite rotaciones de la mano.
    world = getattr(result, "hand_world_landmarks", None)
    hand = world[0] if world else result.hand_landmarks[0]
    point = lambda index: (hand[index].x, hand[index].y, getattr(hand[index], "z", 0.0))
    wrist = point(0)
    scale = math.dist(wrist, point(9))
    if not math.isfinite(scale) or scale < 1e-6:
        return None
    for pip, tip in ((6, 8), (10, 12), (14, 16), (18, 20)):
        proximal = math.dist(wrist, point(pip))
        distal = math.dist(wrist, point(tip))
        if not math.isfinite(distal) or not math.isfinite(proximal) or proximal < 1e-6:
            return None
        if distal >= proximal * 1.1:
            return False
    return True


class FistHold:
    def __init__(self, hold_ms=1000, release_ms=300, max_gap_ms=250):
        self.hold_ms, self.release_ms, self.max_gap_ms = hold_ms, release_ms, max_gap_ms
        self._since = self._released_since = self._last = None
        self._identity = None
        self._latched = False

    def update(self, timestamp, closed, identity=None) -> bool:
        if (self._last is not None and timestamp - self._last > self.max_gap_ms
                or identity != self._identity):
            self._since = self._released_since = None
        self._last, self._identity = timestamp, identity
        if closed is None:
            self._since = self._released_since = None
            return False
        if closed:
            self._released_since = None
            if self._latched:
                return False
            if self._since is None:
                self._since = timestamp
            if timestamp - self._since >= self.hold_ms:
                self._latched = True
                return True
        else:
            self._since = None
            if self._released_since is None:
                self._released_since = timestamp
            if timestamp - self._released_since >= self.release_ms:
                self._latched = False
        return False


class PresentationController:
    def __init__(self, detector: GestureDetector, sender, config: PresentationConfig, *, fist_control=True):
        self.detector, self.sender, self.config = detector, sender, config
        self.hold = FistHold(config.fist_hold_ms, config.release_ms)
        self.mode = "PAUSADO"
        self._deadline = None
        self._last_count = None
        self.fist_control = fist_control
        self._last_fist = "initial"
        self.fist_candidate = False
        self.detector.set_paused(True)
        if not fist_control:
            self.toggle(0)

    def toggle(self, timestamp):
        self.detector.set_paused(True)
        if self.mode == "PAUSADO":
            self.mode = "PREPARANDO"
            self._deadline = timestamp + self.config.countdown * 1000
            self._last_count = None
            print("[CONTROL] Cuenta regresiva: enfocá Canva.", flush=True)
        else:
            self.mode = "PAUSADO"
            self._deadline = None
            print("[CONTROL] PAUSADO: no se enviarán teclas.", flush=True)

    def update(self, timestamp, result, *, mirror):
        self.detector.reason = ""
        position, identity = hand_sample(result, mirror=mirror)
        closed = False
        if self.fist_control:
            closed = fist_sample(result)
            if closed != self._last_fist:
                description = {True: "candidato a puño", False: "mano extendida", None: "sin clasificación"}[closed]
                print(f"[MANO {timestamp} ms] {description}", flush=True)
                self._last_fist = closed
            if self.hold.update(timestamp, closed, identity):
                self.toggle(timestamp)
        self.fist_candidate = closed is True
        if self.mode == "PREPARANDO":
            remaining = max(0, math.ceil((self._deadline - timestamp) / 1000))
            if remaining != self._last_count:
                print(f"[CONTROL] Inicio en {remaining} s", flush=True)
                self._last_count = remaining
            if remaining == 0:
                self.mode = "ACTIVO"
                print("[CONTROL] ACTIVO: estabilizá la mano para el primer barrido.", flush=True)
        if self.mode != "ACTIVO":
            if self.detector.state != State.PAUSED:
                self.detector.set_paused(True)
            return None
        if self.detector.state == State.PAUSED:
            self.detector.set_paused(False)
        if closed is not False and position is not None:
            # Una clasificación aislada no debe borrar un barrido ni alternar
            # el modo de control. No incorporar esta muestra ni emitir acciones.
            # Al volver a observar una mano extendida, max_gap_ms sigue limitando
            # cuánto tiempo puede continuar la trayectoria (también a 15 FPS).
            return None
        event = self.detector.update(timestamp, position, identity)
        if event is not None:
            try:
                self.sender.send(event.action)
            except Exception:
                self.mode = "PAUSADO"
                self.detector.set_paused(True)
                raise
        return event
