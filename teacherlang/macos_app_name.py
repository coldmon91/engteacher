"""Overrides the macOS app name shown in the Dock tooltip and the app menu."""
from __future__ import annotations

import ctypes
import ctypes.util
import sys

_BUNDLE_NAME_KEYS = ("CFBundleName", "CFBundleDisplayName")


def set_macos_app_name(name: str) -> bool:
    """Returns True when the name was applied; call before creating the Tk root.

    A script run by the Python interpreter inherits the interpreter bundle's name ("Python").
    The main bundle's info dictionary is mutable at runtime, so overriding it renames the app.
    """
    if sys.platform != "darwin":
        return False
    try:
        return _override_bundle_names(name)
    except (OSError, AttributeError):
        return False


def _override_bundle_names(name: str) -> bool:
    objc = ctypes.CDLL(ctypes.util.find_library("objc"))
    ctypes.CDLL(ctypes.util.find_library("Foundation"))
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]

    def send(receiver: int, selector: bytes, *args: int | bytes) -> int | None:
        message = ctypes.cast(objc.objc_msgSend, ctypes.CFUNCTYPE(
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
            *[ctypes.c_char_p if isinstance(a, bytes) else ctypes.c_void_p for a in args]))
        return message(receiver, objc.sel_registerName(selector), *args)

    bundle = send(objc.objc_getClass(b"NSBundle"), b"mainBundle")
    info = send(bundle, b"infoDictionary") if bundle else None
    if not info:
        return False
    ns_string = objc.objc_getClass(b"NSString")
    value = send(ns_string, b"stringWithUTF8String:", name.encode("utf-8"))
    for key in _BUNDLE_NAME_KEYS:
        key_object = send(ns_string, b"stringWithUTF8String:", key.encode("ascii"))
        send(info, b"setObject:forKey:", value, key_object)
    return True
