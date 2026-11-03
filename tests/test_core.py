import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from gesto.keyboard import probe_keyboard
from gesto.model import verify_model


class ModelTests(unittest.TestCase):
    def test_missing_model_explains_how_to_download(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(FileNotFoundError, "download-model"):
                verify_model(Path(directory) / "missing.task")

    def test_corrupt_model_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corrupt.task"
            path.write_bytes(b"not a model")
            with self.assertRaisesRegex(ValueError, "Checksum incorrecto"):
                verify_model(path)


class KeyboardTests(unittest.TestCase):
    def test_simulation_needs_no_desktop_or_pyautogui(self):
        # Si el modo de simulación importa PyAutoGUI o espera, la prueba falla.
        with patch.dict("sys.modules", {"pyautogui": None}), \
                patch("gesto.keyboard.time.sleep") as sleep, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            probe_keyboard("next", send=False, countdown=5)
        sleep.assert_not_called()
        self.assertIn("No se enviaron teclas", output.getvalue())

    def test_real_mode_sends_one_key_after_countdown(self):
        fake = MagicMock()
        fake.KEYBOARD_KEYS = ["left", "right"]
        fake.FailSafeException = type("FailSafeException", (Exception,), {})
        events = []
        fake.press.side_effect = lambda key: events.append(key)
        with patch.dict("sys.modules", {"pyautogui": fake}), \
                patch("gesto.keyboard.time.sleep", side_effect=lambda _: events.append("wait")), \
                contextlib.redirect_stdout(io.StringIO()):
            probe_keyboard("previous", send=True, countdown=2)
        self.assertEqual(events, ["wait", "wait", "left"])
        fake.press.assert_called_once_with("left")

    def test_interrupting_countdown_sends_nothing(self):
        fake = MagicMock()
        fake.KEYBOARD_KEYS = ["left", "right"]
        with patch.dict("sys.modules", {"pyautogui": fake}), \
                patch("gesto.keyboard.time.sleep", side_effect=KeyboardInterrupt), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                probe_keyboard("next", send=True, countdown=5)
        fake.press.assert_not_called()


class CameraTests(unittest.TestCase):
    def test_presentation_preview_does_not_create_an_opencv_window(self):
        import numpy as np
        from gesto.gestures import GestureDetector
        from gesto.config import PresentationConfig
        from gesto.vision import run_camera

        detector = GestureDetector()
        controller = MagicMock(detector=detector, config=PresentationConfig(), mode="PAUSADO",
                               fist_control=False, fist_candidate=False)
        controller.update.return_value = None
        capture = MagicMock()
        capture.isOpened.return_value = True
        capture.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
        with patch.dict("os.environ", {"DISPLAY": ":test"}), \
                patch("gesto.vision.create_landmarker"), \
                patch("gesto.vision.detect_frame", return_value=SimpleNamespace(hand_landmarks=[])), \
                patch("cv2.VideoCapture", return_value=capture), \
                patch("cv2.namedWindow") as window, patch("cv2.waitKey") as wait, \
                patch("gesto.preview.PresentationPreview") as overlay, \
                contextlib.redirect_stdout(io.StringIO()):
            overlay.return_value.show.return_value = ord("q")
            run_camera(0, mirror=True, confidence=0.6, detector=detector,
                       controller=controller, preview=True)
        window.assert_not_called()
        wait.assert_not_called()
        overlay.return_value.close.assert_called_once()
        capture.release.assert_called_once()

    def test_presentation_without_preview_does_not_open_windows(self):
        import numpy as np
        from gesto.gestures import GestureDetector
        from gesto.config import PresentationConfig
        from gesto.vision import run_camera

        detector = GestureDetector()
        controller = MagicMock(detector=detector, config=PresentationConfig(), mode="PAUSADO")
        controller.update.side_effect = KeyboardInterrupt
        capture = MagicMock()
        capture.isOpened.return_value = True
        capture.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
        with patch.dict("os.environ", {}, clear=True), \
                patch("gesto.vision.create_landmarker"), \
                patch("gesto.vision.detect_frame", return_value=SimpleNamespace(hand_landmarks=[])), \
                patch("cv2.VideoCapture", return_value=capture), \
                patch("cv2.namedWindow") as window, patch("cv2.imshow") as show, \
                patch("cv2.waitKey") as wait, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                run_camera(0, mirror=True, confidence=0.6, detector=detector,
                           controller=controller, preview=False)
        window.assert_not_called()
        show.assert_not_called()
        wait.assert_not_called()
        capture.release.assert_called_once()

    def test_closing_window_with_x_exits_cleanly(self):
        import cv2
        import numpy as np
        from gesto.vision import run_camera

        capture = MagicMock()
        capture.isOpened.return_value = True
        capture.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
        with patch.dict("os.environ", {"DISPLAY": ":test"}), \
                patch("gesto.vision.create_landmarker"), \
                patch("gesto.vision.detect_frame", return_value=SimpleNamespace(hand_landmarks=[])), \
                patch("cv2.VideoCapture", return_value=capture), \
                patch("cv2.namedWindow"), patch("cv2.imshow"), \
                patch("cv2.waitKey", return_value=-1), \
                patch("cv2.getWindowProperty", side_effect=cv2.error("NULL guiReceiver")), \
                patch("cv2.destroyAllWindows") as close, \
                contextlib.redirect_stdout(io.StringIO()):
            run_camera(0, mirror=True, confidence=0.6)
        capture.release.assert_called_once()
        close.assert_called_once()

    def test_simulation_recognizes_swipe_without_using_keyboard(self):
        import numpy as np
        from gesto.gestures import GestureDetector
        from gesto.vision import run_camera

        positions = [0.5] * 16 + [0.5 - 0.4 * index / 15 for index in range(1, 16)]
        results = [SimpleNamespace(
            hand_landmarks=[[SimpleNamespace(x=x, y=0.5) for _ in range(21)]],
            handedness=[[SimpleNamespace(category_name="Right")]],
        ) for x in positions]
        times = [0.0]
        for index in range(len(positions)):
            times.extend([index * 0.03, index * 0.03])
        capture = MagicMock()
        capture.isOpened.return_value = True
        capture.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
        with patch.dict("os.environ", {"DISPLAY": ":test"}), \
                patch.dict("sys.modules", {"pyautogui": None}), \
                patch("gesto.vision.create_landmarker"), \
                patch("gesto.vision.detect_frame", side_effect=results), \
                patch("gesto.vision.time.monotonic", side_effect=times), \
                patch("cv2.VideoCapture", return_value=capture), \
                patch("cv2.namedWindow"), patch("cv2.imshow"), \
                patch("cv2.getWindowProperty", return_value=1), \
                patch("cv2.waitKey", side_effect=[-1] * (len(positions) - 1) + [ord("q")]), \
                patch("cv2.destroyAllWindows") as close, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            run_camera(0, mirror=True, confidence=0.6, detector=GestureDetector())
        self.assertEqual(output.getvalue().count("[SIMULACION"), 1)
        self.assertIn("AVANZAR", output.getvalue())
        self.assertIn("[ESTADO", output.getvalue())
        capture.release.assert_called_once()
        close.assert_called_once()

    def test_unavailable_camera_is_released_without_opening_window(self):
        from gesto.vision import run_camera

        capture = MagicMock()
        capture.isOpened.return_value = False
        with patch.dict("os.environ", {"DISPLAY": ":test"}), \
                patch("gesto.vision.create_landmarker") as landmarker, \
                patch("cv2.VideoCapture", return_value=capture), \
                patch("cv2.namedWindow") as window:
            with self.assertRaisesRegex(RuntimeError, "No se pudo abrir la cámara"):
                run_camera(0, mirror=True, confidence=0.6)
        capture.release.assert_called_once()
        window.assert_not_called()
        landmarker.return_value.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
