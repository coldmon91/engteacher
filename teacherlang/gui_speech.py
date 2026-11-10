"""The 듣기 button: reads the shown card's improved sentence aloud through SpeechPlayer."""

from collections.abc import Callable

import tkinter as tk
from tkinter import messagebox

from .gui_widgets import FlatButton
from .speech_player import IDLE, LOADING, PLAYING, SpeechPlayer
from .speech_settings import SpeechSettings
from .speech_text import spoken_text

PLAY_LABEL = "듣기"
LOADING_LABEL = "불러오는 중…"
STOP_LABEL = "중지"
POLL_MS = 100
_LABELS = {IDLE: PLAY_LABEL, LOADING: LOADING_LABEL, PLAYING: STOP_LABEL}


class SpeechControl:
    """Keeps the button in step with the player; playback always belongs to the shown card.

    Errors of a click open a dialog; errors of auto play go to `show_status`, which also
    clears once playback succeeds.
    """

    def __init__(self, root: tk.Tk, button: FlatButton, player: SpeechPlayer,
                 settings: SpeechSettings, show_status: Callable[[str], None]):
        self._root = root
        self._button = button
        self._player = player
        self._settings = settings
        self._show_status = show_status
        self._text = ""
        self._manual = False
        self._after_id: str | None = None
        self._refresh()

    @property
    def auto_play(self) -> bool:
        return self._settings.auto_play

    def set_settings(self, settings: SpeechSettings) -> None:
        self._settings = settings

    def show_card(self, record: dict | None) -> None:
        """Stops the previous card's playback and arms the button for this card."""
        self._player.stop()
        self._text = spoken_text(record) if record is not None else ""
        self._refresh()

    def toggle(self) -> None:
        if self._player.state == IDLE:
            self.play(manual=True)
        else:
            self._player.stop()
            self._refresh()

    def play(self, manual: bool) -> None:
        if not self._text:
            return
        self._manual = manual
        self._player.play(self._text, self._settings)
        self._tick()

    def close(self) -> None:
        self._player.stop()
        try:
            self._cancel_tick()
        except tk.TclError:
            pass  # The window is already destroyed, and its timers with it.

    def _tick(self) -> None:
        self._cancel_tick()  # A direct call replaces any pending one.
        error = self._player.poll()
        if error is not None:
            self._report(error)
        elif self._player.state == PLAYING:
            self._show_status("")
        self._refresh()
        if self._player.state != IDLE:
            self._after_id = self._root.after(POLL_MS, self._tick)

    def _cancel_tick(self) -> None:
        if self._after_id is not None:
            self._root.after_cancel(self._after_id)
            self._after_id = None

    def _report(self, message: str) -> None:
        if self._manual:
            messagebox.showerror("TeacherLang", message, parent=self._root)
        else:
            self._show_status(message)

    def _refresh(self) -> None:
        state = self._player.state
        self._button.configure(text=_LABELS[state])
        # Loading cannot be cancelled from the button; moving to another card cancels it.
        self._button.set_enabled(bool(self._text) and state != LOADING)
