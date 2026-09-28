"""Borderless controls for the GUI viewer."""

from collections.abc import Callable

import tkinter as tk

from .gui_theme import Palette


class FlatButton(tk.Label):
    """A text button without a bezel: accent color on hover, fires on release inside it."""

    def __init__(self, parent: tk.Misc, palette: Palette, text: str,
                 command: Callable[[], None], **options):
        options.setdefault("padx", 6)
        options.setdefault("pady", 2)
        super().__init__(parent, text=text, bg=palette.background, cursor="hand2", **options)
        self._palette = palette
        self._command = command
        self._color = palette.text
        self._enabled = True
        self._hovered = False
        self.bind("<Enter>", lambda _event: self._set_hovered(True))
        self.bind("<Leave>", lambda _event: self._set_hovered(False))
        self.bind("<ButtonRelease-1>", self._on_release)
        self._refresh()

    def set_enabled(self, enabled: bool) -> None:
        if enabled != self._enabled:
            self._enabled = enabled
            self.configure(cursor="hand2" if enabled else "")
            self._refresh()

    def set_color(self, color: str) -> None:
        """The resting color; hover and disabled colors override it."""
        if color != self._color:
            self._color = color
            self._refresh()

    def _set_hovered(self, hovered: bool) -> None:
        self._hovered = hovered
        self._refresh()

    def _on_release(self, event: tk.Event) -> None:
        # Dragging off the button before releasing cancels the click, as with native buttons.
        released_inside = self.winfo_containing(event.x_root, event.y_root) is self
        if self._enabled and released_inside:
            self._command()

    def _refresh(self) -> None:
        if not self._enabled:
            color = self._palette.disabled
        elif self._hovered:
            color = self._palette.accent
        else:
            color = self._color
        if self.cget("fg") != color:
            self.configure(fg=color)
