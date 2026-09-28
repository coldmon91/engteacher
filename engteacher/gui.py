"""Desktop window that shows lessons as the hook logs them.

Run it from any terminal: python3 -m engteacher.gui
"""

import argparse
import signal
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from .card_browser import ALL_MODE, NOTES_MODE, CardBrowser
from .config import load_config
from .follow import LessonFollower
from .gui_settings import GuiSettings, clamp_font_size, load_gui_settings, save_gui_settings
from .gui_theme import FONT_TAGS, SAVED_COLOR, TAG_COLORS, CardFonts, palette_for
from .model_settings import ModelSettings, load_model_settings, save_model_settings
from .notes import NoteStore
from .render import (DETAIL, FIELD, HEADER, HEADLINE, ITEM, SECTION, Block, has_alternatives,
                     lesson_blocks)
from .storage_settings import StorageSettings, load_storage_settings, save_storage_settings

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import messagebox

    from .gui_settings_dialog import SettingsDialog
    from .gui_widgets import FlatButton
except ImportError:  # Homebrew Python ships Tk as a separate formula.
    tk = None

EMPTY_DECK_MESSAGE = "아직 교정 기록이 없습니다."
SHOW_ALTERNATIVES_LABEL = "대안 ▸"
HIDE_ALTERNATIVES_LABEL = "대안 ▾"
EMPTY_NOTES_MESSAGE = "저장한 카드가 없습니다. ☆ 버튼이나 s 키로 카드를 저장하세요."
NOTES_ERROR_MESSAGE = "노트 파일을 읽을 수 없습니다: {path}"
SAVE_LABEL = "☆"
SAVED_LABEL = "★"
SETTINGS_LABEL = "⚙"
# Shortcut letters, plus the jamo the same keys type under the Korean 2-set layout.
SAVE_KEYS = frozenset("sSㄴ")
MODE_KEYS = frozenset("nNㅜ")
# Control, Command, and Option: a shortcut letter held with these belongs to something else.
SHORTCUT_MODIFIER_MASK = 0x4 | 0x8 | 0x10
BAR_PADX = 14
CARD_PADX = 22
CARD_PADY = 16
ICON_SIZE_STEP = 5


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
                 interval_ms: int, font_size: int, on_open_settings: Callable[[], None],
                 note_store: NoteStore):
        self._root = root
        self._follower = follower
        self._watch_label = watch_label
        self._interval_ms = interval_ms
        self._browser = CardBrowser(note_store)
        self._notes_path = note_store.path
        self._watch_error = ""
        self._show_alternatives = False
        self._palette = palette_for(root.tk.call("tk", "windowingsystem"))
        palette = self._palette
        root.configure(bg=palette.background)

        self._fonts = CardFonts(tkfont.nametofont("TkTextFont"), font_size)
        ui_font = tkfont.nametofont("TkDefaultFont")
        self._ui_font = ui_font.copy()
        self._ui_bold = ui_font.copy()
        self._ui_bold.configure(weight="bold")
        self._icon_font = ui_font.copy()
        self._icon_font.configure(size=ui_font.actual("size") + ICON_SIZE_STEP)

        def button(parent: "tk.Misc", text: str, command: Callable[[], None],
                   font: "tkfont.Font") -> FlatButton:
            return FlatButton(parent, palette, text, command, font=font)

        def separator() -> "tk.Frame":
            return tk.Frame(root, height=1, bg=palette.separator)

        # Bottom widgets are packed first so shrinking the window clips the card, not the bars.
        footer = tk.Frame(root, bg=palette.background)
        footer.pack(side="bottom", fill="x", padx=BAR_PADX, pady=(6, 10))
        self._alternatives_button = button(footer, SHOW_ALTERNATIVES_LABEL,
                                           self._toggle_alternatives, self._ui_font)
        self._alternatives_button.pack(side="left")
        self._newest_button = button(footer, "최신", self._show_newest, self._ui_font)
        self._newest_button.pack(side="right")
        nav_center = tk.Frame(footer, bg=palette.background)
        nav_center.pack(expand=True)
        self._older_button = button(nav_center, "‹", self._show_older, self._icon_font)
        self._older_button.pack(side="left")
        self._position = tk.Label(nav_center, width=10, font=self._ui_font,
                                  bg=palette.background, fg=palette.secondary)
        self._position.pack(side="left")
        self._newer_button = button(nav_center, "›", self._show_newer, self._icon_font)
        self._newer_button.pack(side="left")

        # Shown only while something is wrong; a healthy window has no status line.
        self._status = tk.Label(root, anchor="w", justify="left", font=self._ui_font,
                                bg=palette.background, fg=TAG_COLORS["red"])
        # A long path wraps at the window width instead of being clipped.
        self._status.bind("<Configure>",
                          lambda event: self._status.configure(wraplength=event.width))
        self._footer = footer
        self._bottom_rule = separator()
        self._bottom_rule.pack(side="bottom", fill="x")

        tool_bar = tk.Frame(root, bg=palette.background)
        tool_bar.pack(side="top", fill="x", padx=BAR_PADX, pady=(8, 4))
        self._mode_buttons = {
            mode: button(tool_bar, label, lambda mode=mode: self._select_mode(mode), self._ui_font)
            for label, mode in (("전체", ALL_MODE), ("노트", NOTES_MODE))
        }
        for mode_button in self._mode_buttons.values():
            mode_button.pack(side="left")
        button(tool_bar, SETTINGS_LABEL, on_open_settings, self._icon_font).pack(side="right")
        self._save_button = button(tool_bar, SAVE_LABEL, self._toggle_saved, self._icon_font)
        self._save_button.pack(side="right")
        separator().pack(side="top", fill="x")

        # Bound on the root only, so keys typed in the settings dialog do not flip cards.
        root.bind("<Left>", lambda _event: self._show_older())
        root.bind("<Right>", lambda _event: self._show_newer())
        root.bind("<End>", lambda _event: self._show_newest())
        root.bind("<KeyPress>", self._on_key)

        card = tk.Frame(root, bg=palette.background)
        card.pack(fill="both", expand=True)
        self._text = tk.Text(card, wrap="word", font=self._fonts.body, padx=CARD_PADX,
                             pady=CARD_PADY, borderwidth=0, highlightthickness=0,
                             bg=palette.background, fg=palette.text, cursor="arrow",
                             state="disabled")
        self._scrollbar = tk.Scrollbar(card, command=self._text.yview)
        self._text.configure(yscrollcommand=self._update_scrollbar)
        self._text.pack(side="left", fill="both", expand=True)
        # The headline's right tab stop follows the card width.
        self._text.bind("<Configure>", lambda _event: self._place_header_tab())
        for tag, color in TAG_COLORS.items():
            self._text.tag_configure(tag, foreground=color)
        self._text.tag_configure("bold", font=self._fonts.bold)
        self._configure_layout_tags()
        self._render_card()

    def set_font_size(self, size: int) -> None:
        self._fonts.resize(size)
        self._configure_layout_tags()

    def show_history(self, limit: int) -> None:
        try:
            self._add_lessons(self._follower.history(limit))
            self._set_watch_error("")
        except OSError as error:
            self._set_watch_error(f"cannot read {self._watch_label}: {error}")

    def start_polling(self) -> None:
        self._root.after(self._interval_ms, self._poll)

    def _poll(self) -> None:
        try:
            self._add_lessons(self._follower.poll())
            self._set_watch_error("")
        except OSError as error:
            # Keep the window alive; the next poll retries.
            self._set_watch_error(f"cannot read {self._watch_label}: {error}")
        self._root.after(self._interval_ms, self._poll)

    def _add_lessons(self, lessons: list[dict]) -> None:
        if not lessons:
            return
        if self._browser.add_lessons(lessons):
            self._render_card()
        else:
            # A user reading an older card keeps it; only the count changes.
            self._update_nav()

    def _show_older(self) -> None:
        if self._browser.deck.older():
            self._render_card()

    def _show_newer(self) -> None:
        if self._browser.deck.newer():
            self._render_card()

    def _show_newest(self) -> None:
        if self._browser.deck.newest():
            self._render_card()

    def _on_key(self, event: "tk.Event") -> None:
        if event.state & SHORTCUT_MODIFIER_MASK:
            return
        if event.char in SAVE_KEYS:
            self._toggle_saved()
        elif event.char in MODE_KEYS:
            self._toggle_mode()

    def _select_mode(self, mode: str) -> None:
        if self._browser.set_mode(mode):
            self._render_card()

    def _toggle_mode(self) -> None:
        if self._browser.toggle_mode():
            self._render_card()

    def _toggle_saved(self) -> None:
        try:
            self._browser.toggle_saved()
        except OSError as error:
            messagebox.showerror("engteacher", f"노트를 저장하지 못했습니다.\n{error}",
                                 parent=self._root)
        self._update_save_button()

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
        record = self._browser.current()
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        if record is None:
            self._text.insert("end", self._empty_card_message(), ("dim",))
        else:
            self._insert_lesson(record)
        self._text.configure(state="disabled")

    def _empty_card_message(self) -> str:
        if self._browser.mode == ALL_MODE:
            return EMPTY_DECK_MESSAGE
        if self._browser.notes_error is not None:
            return f"{self._notes_error_message()}\n{self._browser.notes_error}"
        return EMPTY_NOTES_MESSAGE

    def _notes_error_message(self) -> str:
        return NOTES_ERROR_MESSAGE.format(path=self._notes_path)

    def _insert_lesson(self, record: dict) -> None:
        """Writes one block per line; each line carries its kind's tag for margins and spacing."""
        blocks = lesson_blocks(record, show_alternatives=self._show_alternatives)
        header = next((block for block in blocks if block.kind == HEADER), None)
        previous_kind = ""
        for index, block in enumerate(block for block in blocks if block.kind != HEADER):
            if index:
                self._text.insert("end", "\n", (previous_kind,))
            self._insert_block(block, header)
            previous_kind = block.kind

    def _insert_block(self, block: Block, header: Block | None) -> None:
        def insert(text: str, *tags: str | None) -> None:
            self._text.insert("end", text, (block.kind, *(tag for tag in tags if tag)))

        if block.kind == FIELD:
            insert(block.label, "label")
            insert("\t")
        elif block.kind == SECTION:
            insert(block.label)
        elif block.kind == ITEM:
            insert("·  ", "label")
        for span in block.spans:
            insert(span.text, span.tag)
        if block.kind == HEADLINE and header is not None:
            # The time and project sit at the right end of the headline.
            insert("\t")
            for span in header.spans:
                insert(span.text, "meta")

    def _configure_layout_tags(self) -> None:
        """Sizes margins and spacing from the current fonts; rerun after a font change."""
        fonts = self._fonts
        line = fonts.body.metrics("linespace")
        label_column = max(fonts.body.measure(label) for label in ("원문", "개선")) + line
        bullet = fonts.body.measure("·  ")
        indent = fonts.body.measure("0")
        text = self._text
        text.tag_configure(HEADLINE, font=fonts.headline, spacing3=line // 2)
        text.tag_configure("meta", font=fonts.small, foreground=self._palette.secondary)
        text.tag_configure(FIELD, lmargin2=label_column, tabs=(label_column,),
                           spacing1=line // 5)
        text.tag_configure(SECTION, font=fonts.section, foreground=self._palette.secondary,
                           spacing1=line, spacing3=line // 5)
        text.tag_configure(ITEM, lmargin1=indent, lmargin2=indent + bullet, spacing1=line // 5)
        text.tag_configure(DETAIL, lmargin1=indent + bullet, lmargin2=indent + bullet)
        text.tag_configure("label", foreground=self._palette.secondary)
        # Character colors win over the line colors above; tags made later take priority.
        for tag in (*TAG_COLORS, *FONT_TAGS, "label", "meta"):
            text.tag_raise(tag)
        self._place_header_tab()

    def _place_header_tab(self) -> None:
        content_width = self._text.winfo_width() - 2 * CARD_PADX
        if content_width > 0:
            self._text.tag_configure(HEADLINE, tabs=(content_width, "right"))

    def _update_nav(self) -> None:
        deck = self._browser.deck
        prefix = "노트 " if self._browser.mode == NOTES_MODE else ""
        self._position.configure(text=f"{prefix}{deck.position()} / {len(deck)}")
        self._older_button.set_enabled(not deck.is_at_oldest())
        at_newest = deck.is_at_newest()
        self._newer_button.set_enabled(not at_newest)
        self._newest_button.set_enabled(not at_newest)
        for mode, mode_button in self._mode_buttons.items():
            selected = mode == self._browser.mode
            mode_button.configure(font=self._ui_bold if selected else self._ui_font)
            mode_button.set_color(self._palette.text if selected else self._palette.secondary)
        self._update_alternatives_button()
        self._update_save_button()

    def _update_save_button(self) -> None:
        saved = self._browser.is_current_saved()
        self._save_button.configure(text=SAVED_LABEL if saved else SAVE_LABEL)
        self._save_button.set_color(SAVED_COLOR if saved else self._palette.text)
        self._save_button.set_enabled(self._browser.can_save())
        self._show_status()  # Saving can reveal an unreadable notes file.

    def _update_alternatives_button(self) -> None:
        record = self._browser.current()
        available = record is not None and has_alternatives(record)
        label = HIDE_ALTERNATIVES_LABEL if self._show_alternatives else SHOW_ALTERNATIVES_LABEL
        self._alternatives_button.configure(text=label)
        self._alternatives_button.set_enabled(available)

    def _update_scrollbar(self, first: str, last: str) -> None:
        """Shows the scrollbar only when the card is taller than its area."""
        self._scrollbar.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            self._scrollbar.pack_forget()
        elif not self._scrollbar.winfo_manager():
            self._scrollbar.pack(side="right", fill="y", before=self._text)

    def _set_watch_error(self, message: str) -> None:
        self._watch_error = message
        self._show_status()

    def _show_status(self) -> None:
        """An unreadable notes file outranks the log error until it is fixed."""
        message = (self._notes_error_message() if self._browser.notes_error is not None
                   else self._watch_error)
        if self._status.cget("text") != message:
            self._status.configure(text=message)
        if message and not self._status.winfo_manager():
            self._status.pack(side="bottom", fill="x", padx=BAR_PADX, pady=(4, 0),
                              after=self._footer)
        elif not message and self._status.winfo_manager():
            self._status.pack_forget()


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
                          on_open_settings=controller.open_dialog,
                          note_store=NoteStore(config.notes_path))
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
