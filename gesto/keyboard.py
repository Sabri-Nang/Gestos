"""Prueba aislada: una acción equivale a una pulsación de tecla."""

import os
import sys
import time
from importlib.util import find_spec

KEYS = {"next": "right", "previous": "left"}


class KeyboardSender:
    def __init__(self, keys=None):
        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            print("Sesión Wayland: PyAutoGUI usa X11; verificá la recepción en Canva.")
        try:
            if sys.platform.startswith("linux"):
                from .x11_compat import enable_empty_display_auth
                enable_empty_display_auth()
            import pyautogui
        except SystemExit as exc:
            if find_spec("tkinter") is None:
                raise RuntimeError(
                    "MouseInfo necesita Tkinter. En Ubuntu instalalo desde una terminal: "
                    "sudo apt-get install python3-tk"
                ) from exc
            raise RuntimeError(f"La inicialización de PyAutoGUI terminó con código {exc.code}.") from exc
        except Exception as exc:
            raise RuntimeError(
                "No se pudo inicializar PyAutoGUI. "
                f"Causa: {type(exc).__name__}: {exc}"
            ) from exc
        self.backend = pyautogui
        self.keys = dict(KEYS if keys is None else keys)
        if any(key not in pyautogui.KEYBOARD_KEYS for key in self.keys.values()):
            raise ValueError("La configuración incluye una tecla no admitida por PyAutoGUI.")

    def focus_summary(self):
        """Identificar el foco X11 sin cambiarlo ni guardar títulos de documentos."""
        if not sys.platform.startswith("linux"):
            return "Diagnóstico de foco X11 disponible solo en Linux."
        try:
            display = self.backend.platformModule._display
            window = display.get_input_focus().focus
            if isinstance(window, int):
                return (f"DISPLAY={os.environ.get('DISPLAY')} | sin ventana X11 enfocada "
                        f"(focus={window}); el destino podría ser Wayland nativo.")
            focused_id = window.id
            root_id = display.screen().root.id
            for _ in range(12):
                classes = window.get_wm_class()
                if classes:
                    app = ", ".join(str(item) for item in classes)
                    app = " ".join(app.split())[:120]
                    return f"DISPLAY={os.environ.get('DISPLAY')} | foco=0x{focused_id:x} | aplicación={app}"
                parent = window.query_tree().parent
                if parent.id in (window.id, root_id):
                    break
                window = parent
            return f"DISPLAY={os.environ.get('DISPLAY')} | foco=0x{focused_id:x} | aplicación X11 sin identificar"
        except Exception as exc:
            return f"No se pudo consultar el foco X11: {type(exc).__name__}"

    def send(self, action: str):
        key = self.keys[action]
        print(f"[FOCO] {self.focus_summary()}", flush=True)
        start = time.perf_counter()
        try:
            self.backend.press(key)
        except self.backend.FailSafeException as exc:
            raise RuntimeError("Envío cancelado por el fail-safe de PyAutoGUI.") from exc
        print(f"[TECLA] {action} → {key} | envío={(time.perf_counter() - start) * 1000:.1f} ms",
              flush=True)


def probe_keyboard(action: str, *, send: bool, countdown: int, keys=None, focus_only=False) -> None:
    key = (KEYS if keys is None else keys)[action]
    if not send and not focus_only:
        print(f"Simulación: {action} → tecla {key}. No se enviaron teclas.")
        return
    sender = KeyboardSender(keys)
    print("Enfocá Canva en modo presentación. Ctrl+C cancela desde esta terminal.")
    for remaining in range(countdown, 0, -1):
        label = "Consulta de foco" if focus_only else "Envío"
        print(f"{label} en {remaining}…", flush=True)
        time.sleep(1)
    if focus_only:
        print(f"[FOCO] {sender.focus_summary()}", flush=True)
        print("Diagnóstico terminado. No se enviaron teclas ni se cambió el foco.")
        return
    sender.send(action)
    print(f"Se envió una pulsación: {key}. Verificá el resultado en Canva.")
