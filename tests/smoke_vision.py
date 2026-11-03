"""Inferencia real sobre fotogramas sintéticos; no requiere cámara ni GUI."""

import numpy as np

from gesto.vision import create_landmarker, detect_frame, draw_landmarks
from gesto.gestures import GestureDetector, State, hand_sample


def main():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    detector = GestureDetector()
    with create_landmarker() as landmarker:
        for timestamp in (0, 33, 67):
            result = detect_frame(landmarker, frame, timestamp)
            if result.hand_landmarks:
                raise AssertionError("Se detectó una mano en un fotograma negro.")
            draw_landmarks(frame, result)
            position, identity = hand_sample(result, mirror=True)
            if detector.update(timestamp, position, identity) is not None:
                raise AssertionError("Se emitió un gesto sin mano.")
    if detector.state != State.NO_HAND:
        raise AssertionError("El detector no quedó en SIN MANO.")
    print("OK: modelo verificado; inferencia VIDEO sobre tres fotogramas sin mano; sin gestos.")


if __name__ == "__main__":
    main()
