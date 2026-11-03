import contextlib
import io
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from gesto.config import PresentationConfig
from gesto.gestures import GestureConfig, GestureDetector, State
from gesto.keyboard import KeyboardSender
from gesto.presentation import FistHold, PresentationController, fist_sample


def hand_result(*, closed=False, shift=0):
    points = [SimpleNamespace(x=0.5 + shift, y=0.6, z=0.0) for _ in range(21)]
    points[0].y = 0.8
    for pip, tip in ((6, 8), (10, 12), (14, 16), (18, 20)):
        points[pip].y = 0.4
        points[tip].y = 0.65 if closed else 0.2
    return SimpleNamespace(hand_landmarks=[points],
                           handedness=[[SimpleNamespace(category_name="Right")]])


class FistTests(unittest.TestCase):
    def test_invalid_finger_geometry_does_not_activate_control(self):
        result = hand_result(closed=True)
        result.hand_landmarks[0][6].y = float("nan")
        self.assertIsNone(fist_sample(result))

    def test_open_and_closed_geometry(self):
        self.assertTrue(fist_sample(hand_result(closed=True)))
        self.assertFalse(fist_sample(hand_result()))
        self.assertIsNone(fist_sample(SimpleNamespace(hand_landmarks=[])))

    def test_held_fist_fires_once_until_observed_release(self):
        hold = FistHold(hold_ms=200, release_ms=100)
        actions = [hold.update(t, True, "Right") for t in range(0, 1001, 100)]
        self.assertEqual(sum(actions), 1)
        hold.update(1100, False, "Right")
        hold.update(1200, False, "Right")
        self.assertFalse(hold.update(1300, True, "Right"))
        self.assertFalse(hold.update(1400, True, "Right"))
        self.assertTrue(hold.update(1500, True, "Right"))

    def test_missing_hand_does_not_release_latch(self):
        hold = FistHold(hold_ms=200)
        for t in (0, 100, 200):
            hold.update(t, True, "Right")
        hold.update(300, None)
        self.assertFalse(any(hold.update(t, True, "Right") for t in range(400, 1001, 100)))

    def test_gap_resets_hold_timer(self):
        hold = FistHold(hold_ms=1000)
        hold.update(0, True)
        self.assertFalse(hold.update(1100, True))


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.sender = Mock()
        self.detector = GestureDetector(GestureConfig(distance=0.16, max_duration_ms=1000))
        self.controller = PresentationController(
            self.detector, self.sender,
            PresentationConfig(countdown=1, fist_hold_ms=200, release_ms=100),
        )
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def activate(self):
        for timestamp in (0, 100, 200):
            self.controller.update(timestamp, hand_result(closed=True), mirror=True)
        self.assertEqual(self.controller.mode, "PREPARANDO")
        for timestamp in range(300, 1501, 100):
            self.controller.update(timestamp, hand_result(), mirror=True)
        self.assertEqual(self.controller.mode, "ACTIVO")
        self.assertEqual(self.detector.state, State.READY)

    def swipe(self):
        for index in range(1, 16):
            self.controller.update(1500 + index * 30, hand_result(shift=-0.4 * index / 15), mirror=True)

    def test_startup_and_countdown_send_nothing(self):
        for index in range(10):
            self.controller.update(index * 30, hand_result(shift=-index * 0.04), mirror=True)
        self.assertEqual(self.controller.mode, "PAUSADO")
        self.sender.send.assert_not_called()

    def test_swipe_sends_one_action_after_activation(self):
        self.activate()
        self.sender.send.assert_not_called()
        self.swipe()
        self.sender.send.assert_called_once_with("next")

    def test_one_frame_false_fist_does_not_erase_a_swipe(self):
        self.activate()
        for index in range(1, 16):
            with patch("gesto.presentation.fist_sample", return_value=index == 6):
                self.controller.update(1500 + index * 30,
                                       hand_result(shift=-0.4 * index / 15), mirror=True)
        self.assertEqual(self.controller.mode, "ACTIVO")
        self.sender.send.assert_called_once_with("next")

    def test_no_fist_mode_activates_after_countdown_and_recognizes_barridos(self):
        self.controller = PresentationController(
            self.detector, self.sender,
            PresentationConfig(countdown=1, fist_hold_ms=200, release_ms=100),
            fist_control=False,
        )
        with patch("gesto.presentation.fist_sample") as classify:
            for timestamp in range(0, 1501, 100):
                self.controller.update(timestamp, hand_result(), mirror=True)
            self.assertEqual(self.controller.mode, "ACTIVO")
            self.swipe()
        classify.assert_not_called()
        self.sender.send.assert_called_once_with("next")

    def test_candidate_fist_sends_no_action_and_does_not_claim_manual_pause(self):
        self.activate()
        with patch("gesto.presentation.fist_sample", return_value=True):
            self.controller.update(1530, hand_result(), mirror=True)
        self.assertEqual(self.controller.mode, "ACTIVO")
        self.assertEqual(self.detector.state, State.READY)
        self.assertNotIn("Pausa manual", self.detector.reason)
        self.sender.send.assert_not_called()

    def test_one_frame_false_fist_at_fifteen_fps_preserves_swipe(self):
        self.activate()
        for index in range(1, 9):
            with patch("gesto.presentation.fist_sample", return_value=index == 3):
                self.controller.update(1500 + index * 67,
                                       hand_result(shift=-0.4 * index / 8), mirror=True)
        self.sender.send.assert_called_once_with("next")

    def test_fist_pauses_and_remains_paused_while_held(self):
        self.activate()
        for timestamp in range(1530, 3031, 100):
            self.controller.update(timestamp, hand_result(closed=True), mirror=True)
        self.assertEqual(self.controller.mode, "PAUSADO")
        self.sender.send.assert_not_called()

    def test_fist_can_resume_after_pause_and_release(self):
        self.activate()
        for timestamp in (1530, 1630, 1730):
            self.controller.update(timestamp, hand_result(closed=True), mirror=True)
        self.assertEqual(self.controller.mode, "PAUSADO")
        for timestamp in (1830, 1930):
            self.controller.update(timestamp, hand_result(), mirror=True)
        for timestamp in (2030, 2130, 2230):
            self.controller.update(timestamp, hand_result(closed=True), mirror=True)
        self.assertEqual(self.controller.mode, "PREPARANDO")
        for timestamp in range(2330, 3531, 100):
            self.controller.update(timestamp, hand_result(), mirror=True)
        self.assertEqual(self.controller.mode, "ACTIVO")
        self.assertEqual(self.detector.state, State.READY)
        self.sender.send.assert_not_called()
        for index in range(1, 16):
            self.controller.update(3530 + index * 30, hand_result(shift=0.4 * index / 15), mirror=True)
        self.sender.send.assert_called_once_with("previous")

    def test_sender_failure_pauses_before_propagating(self):
        self.activate()
        self.sender.send.side_effect = RuntimeError("test backend failure")
        with self.assertRaisesRegex(RuntimeError, "backend failure"):
            self.swipe()
        self.assertEqual(self.controller.mode, "PAUSADO")
        self.assertEqual(self.detector.state, State.PAUSED)

    def test_no_hand_does_not_emit_a_key(self):
        self.activate()
        for timestamp in (1530, 1560, 1700):
            self.controller.update(timestamp, SimpleNamespace(hand_landmarks=[], handedness=[]), mirror=True)
        self.sender.send.assert_not_called()

    def test_manual_pause_cancels_activation(self):
        self.controller.toggle(0)
        self.controller.toggle(100)
        self.controller.update(2000, hand_result(), mirror=True)
        self.assertEqual(self.controller.mode, "PAUSADO")
        self.sender.send.assert_not_called()


class SenderTests(unittest.TestCase):
    def test_focus_query_reports_native_or_unfocused_window_without_sending(self):
        backend = self.backend()
        backend.platformModule._display.get_input_focus.return_value.focus = 1
        with patch.dict("sys.modules", {"pyautogui": backend}), \
                patch("gesto.keyboard.sys.platform", "linux"), \
                contextlib.redirect_stdout(io.StringIO()):
            description = KeyboardSender().focus_summary()
        self.assertIn("sin ventana X11 enfocada", description)
        backend.press.assert_not_called()

    def test_focus_query_reports_app_class_without_document_title(self):
        backend = self.backend()
        window = Mock()
        window.id = 99
        window.get_wm_class.return_value = ("chromium", "Chromium")
        backend.platformModule._display.get_input_focus.return_value.focus = window
        with patch.dict("sys.modules", {"pyautogui": backend}), \
                patch("gesto.keyboard.sys.platform", "linux"), \
                contextlib.redirect_stdout(io.StringIO()):
            description = KeyboardSender().focus_summary()
        self.assertIn("Chromium", description)
        window.get_wm_name.assert_not_called()
        backend.press.assert_not_called()

    def test_focus_only_probe_never_sends_a_key(self):
        from gesto.keyboard import probe_keyboard
        backend = self.backend()
        backend.platformModule._display.get_input_focus.return_value.focus = 1
        with patch.dict("sys.modules", {"pyautogui": backend}), \
                patch("gesto.keyboard.time.sleep"), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            probe_keyboard("next", send=False, countdown=1, focus_only=True)
        self.assertIn("No se enviaron teclas", output.getvalue())
        backend.press.assert_not_called()

    def test_missing_tkinter_reports_actionable_error_instead_of_exiting(self):
        import builtins
        original_import = builtins.__import__

        def import_with_exit(name, *args, **kwargs):
            if name == "pyautogui":
                raise SystemExit(1)
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=import_with_exit), \
                patch("gesto.keyboard.find_spec", return_value=None), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "sudo apt-get install python3-tk"):
                KeyboardSender()

    def test_initialization_error_preserves_original_cause(self):
        import builtins
        original_import = builtins.__import__

        def import_with_failure(name, *args, **kwargs):
            if name == "pyautogui":
                raise RuntimeError("Authorization required, but no authorization protocol specified")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=import_with_failure), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "Causa: RuntimeError: Authorization required"):
                KeyboardSender()

    def test_doctor_checks_connection_without_sending_keys(self):
        from gesto.__main__ import main
        backend = self.backend()
        with patch.dict("sys.modules", {"pyautogui": backend}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["doctor", "--keyboard"]), 0)
        backend.press.assert_not_called()

    def backend(self):
        backend = Mock()
        backend.KEYBOARD_KEYS = ["right", "left", "pagedown", "pageup"]
        backend.FailSafeException = type("FailSafeException", (Exception,), {})
        return backend

    def test_semantic_action_sends_one_configured_key(self):
        backend = self.backend()
        with patch.dict("sys.modules", {"pyautogui": backend}), contextlib.redirect_stdout(io.StringIO()):
            sender = KeyboardSender({"next": "pagedown", "previous": "pageup"})
            sender.send("next")
        backend.press.assert_called_once_with("pagedown")

    def test_fail_safe_is_reported(self):
        backend = self.backend()
        backend.press.side_effect = backend.FailSafeException()
        with patch.dict("sys.modules", {"pyautogui": backend}), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "fail-safe"):
                KeyboardSender().send("next")


if __name__ == "__main__":
    unittest.main()
