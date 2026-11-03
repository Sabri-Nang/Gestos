import unittest
from unittest.mock import Mock, patch

import numpy as np

from gesto.preview import PresentationPreview, disable_x11_input


class PreviewTests(unittest.TestCase):
    def preview(self):
        root = Mock()
        root.winfo_id.return_value = 123
        with patch("tkinter.Tk", return_value=root), patch("tkinter.Frame"), \
                patch("tkinter.Label"), patch("gesto.preview.disable_x11_input"), \
                patch("gesto.preview.sys.platform", "linux"):
            preview = PresentationPreview()
        self.addCleanup(preview.close)
        return preview, root

    def test_preview_avoids_managed_frame_and_focus_requests(self):
        preview, root = self.preview()
        root.overrideredirect.assert_called_once_with(True)
        self.assertIn((("-type", "tooltip"),), [(call.args,) for call in root.attributes.call_args_list])
        root.focus_set.assert_not_called()
        root.focus_force.assert_not_called()

    def test_pause_and_close_controls_work_without_keyboard_focus(self):
        preview, root = self.preview()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        with patch("PIL.ImageTk.PhotoImage"):
            preview._request_pause()
            self.assertEqual(preview.show(frame, "LISTO"), ord("p"))
            self.assertEqual(preview.show(frame, "PAUSADO"), -1)
            preview._request_close()
            self.assertEqual(preview.show(frame, "PAUSADO"), ord("q"))
        root.focus_set.assert_not_called()
        root.focus_force.assert_not_called()

    def test_input_hint_never_changes_server_root(self):
        display = Mock()
        window = Mock(id=10)
        parent = Mock(id=1)
        window.query_tree.return_value.parent = parent
        display.create_resource_object.return_value = window
        display.screen.return_value.root.id = 1
        with patch("Xlib.display.Display", return_value=display):
            disable_x11_input(10)
        window.set_wm_hints.assert_called_once_with(flags=1, input=0)
        parent.set_wm_hints.assert_not_called()
        display.close.assert_called_once()

    def test_input_hint_applies_to_own_tk_wrapper(self):
        display = Mock()
        window, parent = Mock(id=10), Mock(id=20)
        window.query_tree.return_value.parent = parent
        display.create_resource_object.return_value = window
        display.screen.return_value.root.id = 1
        with patch("Xlib.display.Display", return_value=display):
            disable_x11_input(10)
        window.set_wm_hints.assert_called_once_with(flags=1, input=0)
        parent.set_wm_hints.assert_called_once_with(flags=1, input=0)
