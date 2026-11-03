import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gesto.config import load_settings


class ConfigTests(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text(text)
            return load_settings(path)

    def test_project_profile_preserves_tested_thresholds(self):
        settings = load_settings()
        self.assertEqual(settings.gestures.distance, 0.10)
        self.assertEqual(settings.gestures.max_duration_ms, 1000)

    def test_invalid_configuration_is_rejected(self):
        for text in ('[unknown]\nx=1', '[camera]\nindex=true', '[camera]\nindex=-1',
                     '[gestures]\ndistance=nan', '[gestures]\nwrong=1',
                     '[presentation]\ncountdown=0', '[keys]\nnext="left"'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.load(text)

    def test_cli_overrides_config_before_opening_camera(self):
        from gesto.__main__ import main
        with patch("gesto.vision.run_camera") as camera, contextlib.redirect_stdout(io.StringIO()):
            code = main(["simulate", "--distance", "0.18", "--no-mirror"])
        self.assertEqual(code, 0)
        options = camera.call_args.kwargs
        self.assertEqual(options["detector"].config.distance, 0.18)
        self.assertFalse(options["mirror"])

    def test_invalid_gesture_options_do_not_connect_keyboard(self):
        from gesto.__main__ import main
        with patch("gesto.keyboard.KeyboardSender") as sender, \
                contextlib.redirect_stderr(io.StringIO()):
            code = main(["present", "--distance", "0.01"])
        self.assertEqual(code, 1)
        sender.assert_not_called()


if __name__ == "__main__":
    unittest.main()
