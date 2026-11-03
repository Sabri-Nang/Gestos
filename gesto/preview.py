"""Vista de presentación flotante que no solicita el foco del teclado."""

import sys


def disable_x11_input(window_id: int) -> None:
    """Marcar exclusivamente la ventana propia y su envoltorio como no enfocables."""
    from Xlib.display import Display
    from Xlib import Xutil
    from .x11_compat import enable_empty_display_auth

    enable_empty_display_auth()
    display = Display()
    try:
        window = display.create_resource_object("window", window_id)
        parent = window.query_tree().parent
        targets = [window]
        if parent.id not in (window.id, display.screen().root.id):
            targets.append(parent)
        for target in targets:
            target.set_wm_hints(flags=Xutil.InputHint, input=0)
        display.sync()
    finally:
        display.close()


class PresentationPreview:
    def __init__(self):
        import tkinter as tk

        self.tk = tk
        self.root = tk.Tk(className="GestoPreview")
        self.closed = False
        self._key = -1
        self._image = None
        self._drag_offset = (0, 0)
        try:
            self.root.withdraw()
            self.root.title("Gesto - diagnóstico")
            self.root.overrideredirect(True)
            self.root.attributes("-topmost", True)
            if sys.platform.startswith("linux"):
                self.root.attributes("-type", "tooltip")
            self.root.geometry("360x318+20+70")
            self.root.configure(background="#17202b", takefocus=0)
            self.root.protocol("WM_TAKE_FOCUS", lambda: None)
            self.root.protocol("WM_DELETE_WINDOW", self._request_close)

            header = tk.Frame(self.root, background="#17202b", height=26, takefocus=0)
            header.pack(fill="x")
            title = tk.Label(header, text="Gesto · arrastrar", foreground="white",
                             background="#17202b", takefocus=0, padx=8)
            title.pack(side="left")
            pause = tk.Label(header, text="Pausa / iniciar", foreground="white",
                             background="#334155", takefocus=0, padx=6, cursor="hand2")
            pause.pack(side="left", padx=4)
            pause.bind("<Button-1>", self._request_pause)
            close = tk.Label(header, text="×", foreground="white", background="#17202b",
                             takefocus=0, padx=8, cursor="hand2")
            close.pack(side="right")
            close.bind("<Button-1>", self._request_close)
            for widget in (header, title):
                widget.bind("<ButtonPress-1>", self._start_drag)
                widget.bind("<B1-Motion>", self._drag)

            self.status = tk.Label(self.root, text="PREPARANDO", foreground="#fbbf24",
                                   background="#17202b", font=("sans", 11, "bold"), takefocus=0)
            self.status.pack(fill="x")
            self.picture = tk.Label(self.root, background="black", takefocus=0, borderwidth=0)
            self.picture.pack(fill="both", expand=True)
            self.root.update_idletasks()
            if sys.platform.startswith("linux"):
                disable_x11_input(self.root.winfo_id())
            self.root.deiconify()
            self.root.update_idletasks()
            if sys.platform.startswith("linux"):
                disable_x11_input(self.root.winfo_id())
        except Exception:
            self.close()
            raise

    def _request_pause(self, event=None):
        self._key = ord("p")

    def _request_close(self, event=None):
        self.closed = True

    def _start_drag(self, event):
        self._drag_offset = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _drag(self, event):
        x, y = event.x_root - self._drag_offset[0], event.y_root - self._drag_offset[1]
        self.root.geometry(f"+{max(0, x)}+{max(0, y)}")

    def show(self, frame, status: str) -> int:
        if self.closed:
            return ord("q")
        from PIL import Image, ImageTk

        try:
            image = Image.fromarray(frame[:, :, ::-1]).resize((360, 270), Image.Resampling.BILINEAR)
            self._image = ImageTk.PhotoImage(image, master=self.root)
            self.picture.configure(image=self._image)
            self.status.configure(text=status, foreground="#4ade80" if status == "LISTO" else "#fbbf24")
            self.root.update_idletasks()
            self.root.update()
        except self.tk.TclError:
            self.closed = True
        key, self._key = self._key, -1
        return ord("q") if self.closed else key

    def close(self):
        self.closed = True
        try:
            self.root.destroy()
        except self.tk.TclError:
            pass
