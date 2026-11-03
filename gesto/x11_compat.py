"""Compatibilidad de python3-xlib 0.15 con las autorizaciones de Mutter/XWayland."""

from functools import wraps


def enable_empty_display_auth() -> None:
    # PyAutoGUI depende de python3-xlib 0.15. Esa versión solo acepta un número
    # de pantalla exacto; Mutter también escribe entradas cuyo número está vacío.
    # Aplicar el mismo fallback que python-xlib mantenido, sin modificar archivos
    # de autorización ni aceptar credenciales de otra familia/host/protocolo.
    # https://github.com/python-xlib/python-xlib/blob/master/Xlib/xauth.py
    from Xlib import error, xauth

    original = xauth.Xauthority.get_best_auth
    if getattr(original, "_gesto_empty_display_auth", False):
        return

    @wraps(original)
    def get_best_auth(self, family, address, dispno, types=(b"MIT-MAGIC-COOKIE-1",)):
        try:
            return original(self, family, address, dispno, types)
        except error.XNoAuthError:
            encoded_address = address.encode() if isinstance(address, str) else address
            for protocol in types:
                for efamily, eaddress, number, name, cookie in self.entries:
                    if (efamily == family and eaddress == encoded_address
                            and number == b"" and name == protocol):
                        return name, cookie
            raise

    get_best_auth._gesto_empty_display_auth = True
    xauth.Xauthority.get_best_auth = get_best_auth
