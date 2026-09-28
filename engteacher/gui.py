"""Desktop window that shows lessons as the hook logs them.

Run it from any terminal: python3 -m engteacher.gui
"""

import argparse
import signal
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from .card_deck import CardDeck
from .config import load_config
from .follow import LessonFollower
from .gui_settings import GuiSettings, clamp_font_size, load_gui_settings, save_gui_settings
from .model_settings import ModelSettings, load_model_settings, save_model_settings
from .render import has_alternatives, lesson_lines
from .storage_settings import StorageSettings, load_storage_settings, save_storage_settings

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import messagebox

    from .gui_settings_dialog import SettingsDialog
except ImportError:  # Homebrew Python ships Tk as a separate formula.
    tk = None

# Mid-tone colors that stay readable on both light and dark system backgrounds.
TAG_COLORS = {
    "dim": "gray55",
    "red": "#d9534f",
    "green": "#3c9d4f",
    "cyan": "#1f9bb5",
    "yellow": "#d08c00",
}
# Tags rendered through a font change instead of a color.
FONT_TAGS = {"bold"}
EMPTY_DECK_MESSAGE = "아직 교정 기록이 없습니다."
SHOW_ALTERNATIVES_LABEL = "대안 보기"
HIDE_ALTERNATIVES_LABEL = "대안 숨기기"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="engteacher-gui", description=__doc__.splitlines()[0])
    parser.add_argument("-n", "--history", type=int, default=20, help="lessons to show at start")
    parser.add_argument("--interval", type=float, default=0.5, help="poll interval in seconds")
    parser.add_argument("--font-size", type=int, help="text size in points (overrides settings)")
    parser.add_argument("--topmost", action="store_true",
                        help="keep the window above others (overrides settings)")
    return parser.parse_args(argv)


def _startup_settings(saved: GuiSettings, args: argparse.Namespace) -> GuiSettings:
    """Command-line options win over saved settings for this run."""
    settings = saved
    if args.topmost:
        settings = replace(settings, always_on_top=True)
    if args.font_size is not None:
        settings = replace(settings, font_size=clamp_font_size(args.font_size))
    return settings


class LessonWindow:
    def __init__(self, root: "tk.Tk", follower: LessonFollower, watch_label: str,
                 interval_ms: int, font_size: int, on_open_settings: Callable[[], None]):
        self._root = root
        self._follower = follower
        self._watch_label = watch_label
        self._interval_ms = interval_ms
        self._deck = CardDeck()
        self._show_alternatives = False

        self._body_font = tkfont.nametofont("TkTextFont").copy()
        self._body_font.configure(size=font_size)
        self._bold_font = self._body_font.copy()
        self._bold_font.configure(weight="bold")

        # Packed first so shrinking the window clips the card, not the bars below it.
        status_bar = tk.Frame(root)
        status_bar.pack(side="bottom", fill="x")
        tk.Button(status_bar, text="설정…", command=on_open_settings).pack(side="right", padx=4)
        self._status = tk.Label(status_bar, anchor="w", padx=8, fg=TAG_COLORS["dim"])
        self._status.pack(side="left", fill="x", expand=True)

        nav_bar = tk.Frame(root)
        nav_bar.pack(side="bottom", fill="x", padx=12, pady=(0, 4))
        self._newest_button = tk.Button(nav_bar, text="최신", command=self._show_newest)
        self._newest_button.pack(side="right")
        self._alternatives_button = tk.Button(nav_bar, text=SHOW_ALTERNATIVES_LABEL,
                                              command=self._toggle_alternatives)
        self._alternatives_button.pack(side="left")
        nav_center = tk.Frame(nav_bar)
        nav_center.pack(expand=True)
        self._older_button = tk.Button(nav_center, text="◀", width=3, command=self._show_older)
        self._older_button.pack(side="left")
        self._position = tk.Label(nav_center, width=10)
        self._position.pack(side="left")
        self._newer_button = tk.Button(nav_center, text="▶", width=3, command=self._show_newer)
        self._newer_button.pack(side="left")

        # Bound on the root only, so keys typed in the settings dialog do not flip cards.
        root.bind("<Left>", lambda _event: self._show_older())
        root.bind("<Right>", lambda _event: self._show_newer())
        root.bind("<End>", lambda _event: self._show_newest())

        card = tk.Frame(root, highlightthickness=1, highlightbackground=TAG_COLORS["dim"],
                        highlightcolor=TAG_COLORS["dim"])
        card.pack(fill="both", expand=True, padx=12, pady=(12, 8))
        self._text = tk.Text(card, wrap="word", font=self._body_font, padx=12, pady=10,
                             borderwidth=0, highlightthickness=0, state="disabled")
        self._scrollbar = tk.Scrollbar(card, command=self._text.yview)
        self._text.configure(yscrollcommand=self._update_scrollbar)
        self._text.pack(side="left", fill="both", expand=True)
        for tag, color in TAG_COLORS.items():
            self._text.tag_configure(tag, foreground=color)
        self._text.tag_configure("bold", font=self._bold_font)
        self._render_card()

    def set_font_size(self, size: int) -> None:
        self._body_font.configure(size=size)
        self._bold_font.configure(size=size)

    def show_history(self, limit: int) -> None:
        try:
            self._add_lessons(self._follower.history(limit))
            self._set_status(f"watching {self._watch_label}")
        except OSError as error:
            self._set_status(f"cannot read {self._watch_label}: {error}")

    def start_polling(self) -> None:
        self._root.after(self._interval_ms, self._poll)

    def _poll(self) -> None:
        try:
            self._add_lessons(self._follower.poll())
            self._set_status(f"watching {self._watch_label}")
        except OSError as error:
            # Keep the window alive; the next poll retries.
            self._set_status(f"cannot read {self._watch_label}: {error}")
        self._root.after(self._interval_ms, self._poll)

    def _add_lessons(self, lessons: list[dict]) -> None:
        if not lessons:
            return
        if self._deck.add(lessons):
            self._render_card()
        else:
            # A user reading an older card keeps it; only the count changes.
            self._update_nav()

    def _show_older(self) -> None:
        if self._deck.older():
            self._render_card()

    def _show_newer(self) -> None:
        if self._deck.newer():
            self._render_card()

    def _show_newest(self) -> None:
        if self._deck.newest():
            self._render_card()

    def _toggle_alternatives(self) -> None:
        self._show_alternatives = not self._show_alternatives
        scroll_top = self._text.yview()[0]
        self._draw_card()
        self._text.yview_moveto(scroll_top)
        self._update_alternatives_button()

    def _render_card(self) -> None:
        """Shows the current card from the top, with its 대안 section folded."""
        self._show_alternatives = False
        self._draw_card()
        self._text.yview_moveto(0)
        self._update_nav()

    def _draw_card(self) -> None:
        record = self._deck.current()
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        if record is None:
            self._text.insert("end", EMPTY_DECK_MESSAGE, ("dim",))
        else:
            self._insert_lesson(record)
        self._text.configure(state="disabled")

    def _insert_lesson(self, record: dict) -> None:
        lines = lesson_lines(record, header_rule=False, show_alternatives=self._show_alternatives)
        for index, line in enumerate(lines):
            if index:
                self._text.insert("end", "\n")
            for span in line:
                self._text.insert("end", span.text, (span.tag,) if span.tag else ())

    def _update_nav(self) -> None:
        self._position.configure(text=f"{self._deck.position()} / {len(self._deck)}")
        self._older_button.configure(state="disabled" if self._deck.is_at_oldest() else "normal")
        at_newest = self._deck.is_at_newest()
        self._newer_button.configure(state="disabled" if at_newest else "normal")
        self._newest_button.configure(state="disabled" if at_newest else "normal")
        self._update_alternatives_button()

    def _update_alternatives_button(self) -> None:
        record = self._deck.current()
        available = record is not None and has_alternatives(record)
        label = HIDE_ALTERNATIVES_LABEL if self._show_alternatives else SHOW_ALTERNATIVES_LABEL
        self._alternatives_button.configure(text=label,
                                            state="normal" if available else "disabled")

    def _update_scrollbar(self, first: str, last: str) -> None:
        """Shows the scrollbar only when the card is taller than its area."""
        self._scrollbar.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            self._scrollbar.pack_forget()
        elif not self._scrollbar.winfo_manager():
            self._scrollbar.pack(side="right", fill="y", before=self._text)

    def _set_status(self, message: str) -> None:
        if self._status.cget("text") != message:
            self._status.configure(text=message)


class SettingsController:
    """Applies settings to the running window and saves every change made in the dialog."""

    def __init__(self, root: "tk.Tk", settings: GuiSettings, settings_path: Path,
                 model_settings_path: Path, storage_settings_path: Path):
        self._root = root
        self._settings = settings
        self._settings_path = settings_path
        self._model_settings_path = model_settings_path
        self._storage_settings_path = storage_settings_path
        self._window: LessonWindow | None = None
        self._dialog: SettingsDialog | None = None

    @property
    def settings(self) -> GuiSettings:
        return self._settings

    def attach(self, window: LessonWindow) -> None:
        self._window = window

    def open_dialog(self) -> None:
        if self._dialog is not None and self._dialog.is_open():
            self._dialog.focus()
            return
        # Read on every open: the files are the source of truth shared with the hook.
        model_settings = load_model_settings(self._model_settings_path)
        storage_settings = load_storage_settings(self._storage_settings_path)
        self._dialog = SettingsDialog(self._root, self._settings, model_settings, storage_settings,
                                      self._change, self._change_model, self._change_storage,
                                      self._saved_model_for)

    def _change(self, settings: GuiSettings) -> None:
        if settings.always_on_top != self._settings.always_on_top:
            self._root.attributes("-topmost", settings.always_on_top)
        if settings.font_size != self._settings.font_size and self._window is not None:
            self._window.set_font_size(settings.font_size)
        self._settings = settings
        try:
            save_gui_settings(self._settings_path, settings)
        except OSError as error:
            # The change still applies to this run; only persistence failed.
            self._show_save_error(error)

    def _change_model(self, settings: ModelSettings) -> None:
        try:
            save_model_settings(self._model_settings_path, settings)
        except (OSError, ValueError) as error:
            self._show_save_error(error)

    def _change_storage(self, settings: StorageSettings) -> None:
        try:
            save_storage_settings(self._storage_settings_path, settings)
        except OSError as error:
            self._show_save_error(error)

    def _saved_model_for(self, provider: str) -> str:
        return load_model_settings(self._model_settings_path, provider).model

    def _show_save_error(self, error: Exception) -> None:
        messagebox.showerror("engteacher", f"설정을 저장하지 못했습니다.\n{error}", parent=self._root)


def _bring_to_front(root: "tk.Tk", keep_on_top: bool) -> None:
    # A window launched from a terminal opens behind it on macOS unless raised once.
    root.lift()
    root.attributes("-topmost", True)
    if not keep_on_top:
        root.after_idle(root.attributes, "-topmost", False)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if tk is None:
        version = f"{sys.version_info.major}.{sys.version_info.minor}"
        print(f"engteacher-gui: tkinter is unavailable. Try: brew install python-tk@{version}",
              file=sys.stderr)
        return 1

    config = load_config()
    root = tk.Tk()
    root.title("engteacher")
    root.geometry("560x680")
    root.bind("<Command-w>", lambda _event: root.destroy())
    # quit() only stops mainloop, so a Ctrl-C landing mid-callback cannot destroy widgets in use.
    # The periodic poll gives Python a chance to run this handler while Tk waits for events.
    signal.signal(signal.SIGINT, lambda *_: root.quit())

    controller = SettingsController(
        root, _startup_settings(load_gui_settings(config.gui_settings_path), args),
        config.gui_settings_path, config.model_settings_path, config.storage_settings_path)
    if root.tk.call("tk", "windowingsystem") == "aqua":
        # Enables the app menu's Settings… item and its Cmd-, shortcut.
        root.createcommand("tk::mac::ShowPreferences", controller.open_dialog)

    window = LessonWindow(root, LessonFollower(config.lessons_path), str(config.lessons_path),
                          interval_ms=int(max(0.1, args.interval) * 1000),
                          font_size=controller.settings.font_size,
                          on_open_settings=controller.open_dialog)
    controller.attach(window)
    window.show_history(args.history)
    window.start_polling()
    _bring_to_front(root, controller.settings.always_on_top)
    root.mainloop()
    try:
        root.destroy()
    except tk.TclError:
        pass  # Already destroyed by the close button or Cmd-W.
    return 0


if __name__ == "__main__":
    sys.exit(main())
