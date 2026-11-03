"""Comprobación gráfica optativa: foco antes/después, sin cámara ni teclas."""

import time

import numpy as np

from gesto.preview import PresentationPreview
from gesto.x11_compat import enable_empty_display_auth


def main():
    from Xlib.display import Display

    enable_empty_display_auth()
    display = Display()
    preview = None
    try:
        def focus_id():
            focus = display.get_input_focus().focus
            return focus if isinstance(focus, int) else focus.id

        before = focus_id()
        preview = PresentationPreview()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        for _ in range(8):
            preview.show(frame, "PRUEBA DE FOCO")
            time.sleep(0.1)
        after = focus_id()
        print(f"Foco antes: 0x{before:x}; después: 0x{after:x}")
        if before != after:
            raise AssertionError("El foco cambió durante la prueba; revisar si hubo interacción externa.")
        print("OK: apertura y actualización de la vista conservan el foco. Sin teclas ni cámara.")
    finally:
        if preview is not None:
            preview.close()
        display.close()


if __name__ == "__main__":
    main()
