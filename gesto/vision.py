"""Captura e inferencia compartidas por diagnóstico, simulación y presentación."""

import os
import sys
import time
import unicodedata

from .model import MODEL_PATH, verify_model
from .gestures import GestureDetector, State, hand_sample

WINDOW = "Gesto - diagnostico de mano"


def create_landmarker(confidence: float = 0.6):
    verify_model()
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import (
        HandLandmarker, HandLandmarkerOptions, RunningMode,
    )

    options = HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=RunningMode.VIDEO,
        num_hands=1,
        min_hand_detection_confidence=confidence,
        min_hand_presence_confidence=confidence,
        min_tracking_confidence=confidence,
    )
    return HandLandmarker.create_from_options(options)


def detect_frame(landmarker, frame, timestamp_ms: int):
    import cv2
    import mediapipe as mp

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    return landmarker.detect_for_video(image, timestamp_ms)


def draw_landmarks(frame, result) -> None:
    import cv2
    from mediapipe.tasks.python.vision.hand_landmarker import HandLandmarksConnections

    height, width = frame.shape[:2]
    for hand in result.hand_landmarks:
        points = [(int(p.x * (width - 1)), int(p.y * (height - 1))) for p in hand]
        for edge in HandLandmarksConnections.HAND_CONNECTIONS:
            cv2.line(frame, points[edge.start], points[edge.end], (0, 220, 0), 2)
        for point in points:
            cv2.circle(frame, point, 4, (0, 180, 255), -1)


def run_camera(camera: int, *, mirror: bool, confidence: float,
               detector: GestureDetector | None = None, controller=None, preview=True) -> None:
    if controller is not None and controller.detector is not detector:
        raise ValueError("El controlador debe compartir el detector de la captura.")
    if preview and sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        raise RuntimeError("No hay sesión gráfica para mostrar el diagnóstico de cámara.")
    import cv2

    capture = None
    window_created = False
    overlay = None
    try:
        with create_landmarker(confidence) as landmarker:
            capture = cv2.VideoCapture(camera)
            if not capture.isOpened():
                raise RuntimeError(
                    f"No se pudo abrir la cámara {camera}. Revisá permisos, otras apps "
                    "que la usen o probá --camera 1."
                )
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            if preview:
                if controller is not None:
                    from .preview import PresentationPreview
                    overlay = PresentationPreview()
                    print("Vista flotante de 360 px sin marco. Arrastrá la barra para moverla; "
                          "controles con mouse: Pausa / iniciar y × para salir.", flush=True)
                else:
                    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
                    window_created = True
            if controller is None:
                print("Diagnóstico sin envío de teclas. Q o Esc para salir con la ventana enfocada.")
            else:
                print(f"Presentación: {controller.config}", flush=True)
                if controller.fist_control:
                    print(f"PAUSADO. Puño cerrado {controller.config.fist_hold_ms / 1000:g} s: "
                          "activar con cuenta regresiva o pausar.", flush=True)
                    print("Abrí la mano después de cada comando de puño. Ctrl+C en terminal: salir.", flush=True)
                else:
                    print("Control por puño desactivado. Inicio tras cuenta regresiva. "
                          "Ctrl+C en terminal: salir.", flush=True)
            if detector is not None:
                print(f"Detector de barridos: {detector.config}")
                if controller is None:
                    print("Mantené la mano quieta hasta LISTO. P pausa o reanuda con la ventana enfocada.")
            start = previous = time.monotonic()
            last_timestamp = -1
            fps = 0.0
            last_action = "-"
            last_action_at = -2000
            last_detail = ""
            last_detail_at = -2000
            while True:
                ok, frame = capture.read()
                if not ok or frame is None:
                    raise RuntimeError("Se interrumpió la lectura de la cámara.")
                # Inferencia y dibujo usan el mismo fotograma, espejado por defecto.
                if mirror:
                    frame = cv2.flip(frame, 1)
                timestamp = max(last_timestamp + 1, int((time.monotonic() - start) * 1000))
                result = detect_frame(landmarker, frame, timestamp)
                last_timestamp = timestamp
                now = time.monotonic()
                instant_fps = 1 / max(now - previous, 1e-6)
                fps = instant_fps if fps == 0 else 0.9 * fps + 0.1 * instant_fps
                previous = now
                if preview:
                    draw_landmarks(frame, result)
                status = "Mano detectada" if result.hand_landmarks else "Sin mano"
                if detector is not None:
                    position, hand_id = hand_sample(result, mirror=mirror)
                    old_state = detector.state
                    event = (controller.update(timestamp, result, mirror=mirror) if controller
                             else detector.update(timestamp, position, hand_id))
                    if detector.state != old_state:
                        print(f"[ESTADO {timestamp} ms] {detector.state}", flush=True)
                    if detector.reason:
                        print(f"[DETALLE {timestamp} ms] {detector.reason}", flush=True)
                        last_detail = unicodedata.normalize("NFKD", detector.reason).encode(
                            "ascii", "ignore").decode()[:72]
                        last_detail_at = timestamp
                    if event is not None:
                        last_action = "AVANZAR" if event.action == "next" else "RETROCEDER"
                        last_action_at = timestamp
                        mode = "PRESENTACION" if controller else "SIMULACION"
                        print(f"[{mode} {timestamp} ms] {last_action} | "
                              f"dx={event.dx:.3f} dy={event.dy:.3f} duracion={event.duration_ms} ms",
                              flush=True)
                    status = str(detector.state)
                    if controller and controller.mode != "ACTIVO":
                        status = controller.mode
                    elif controller and controller.fist_candidate:
                        status = "CONFIRMANDO PUNO"
                if not preview:
                    continue
                cv2.putText(frame, f"{status} | FPS: {fps:.1f}", (12, 28),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
                hint = "Simulacion | P: pausa | Q / Esc: salir" if detector else "Diagnostico | Q / Esc: salir"
                if controller:
                    hint = "Presentacion | controles en la barra flotante"
                cv2.putText(frame, hint, (12, 56),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
                if detector is not None and timestamp - last_action_at < 1500:
                    cv2.putText(frame, last_action, (12, 90), cv2.FONT_HERSHEY_SIMPLEX,
                                0.8, (0, 255, 255), 2)
                if detector is not None and detector.state == State.TRACKING and detector.motion is not None:
                    dx, dy, elapsed = detector.motion
                    cv2.putText(frame,
                                f"Barrido: {abs(dx):.2f}/{detector.config.distance:.2f} | "
                                f"{elapsed}/{detector.config.max_duration_ms} ms", (12, 120),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
                if detector is not None and timestamp - last_detail_at < 2000:
                    cv2.putText(frame, last_detail, (12, 148),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.43, (255, 230, 150), 1)
                if overlay is not None:
                    key = overlay.show(frame, status)
                else:
                    cv2.imshow(WINDOW, frame)
                    key = cv2.waitKey(1) & 0xFF
                if key == ord("p") and detector is not None:
                    if controller:
                        controller.toggle(timestamp)
                    else:
                        detector.set_paused(detector.state != State.PAUSED)
                        print(f"Simulación: {detector.state}", flush=True)
                if key in (ord("q"), 27):
                    break
                if overlay is not None:
                    continue
                try:
                    if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                        break
                except cv2.error:
                    # Qt puede destruir la ventana antes de poder consultar su visibilidad.
                    break
    finally:
        if capture is not None:
            capture.release()
        if overlay is not None:
            overlay.close()
        if window_created:
            cv2.destroyAllWindows()
