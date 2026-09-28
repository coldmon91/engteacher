"""Settings window for the GUI viewer; reports every change through callbacks."""

from collections.abc import Callable

import tkinter as tk
from tkinter import ttk

from .gui_settings import FONT_SIZE_MAX, FONT_SIZE_MIN, GuiSettings, clamp_font_size
from .model_settings import PROVIDERS, ModelSettings, is_valid_model
from .storage_settings import (RETENTION_DAYS_MAX, RETENTION_DAYS_MIN, StorageSettings,
                               clamp_retention_days)


class SettingsDialog:
    def __init__(self, parent: tk.Tk, settings: GuiSettings, model_settings: ModelSettings,
                 storage_settings: StorageSettings,
                 on_change: Callable[[GuiSettings], None],
                 on_model_change: Callable[[ModelSettings], None],
                 on_storage_change: Callable[[StorageSettings], None],
                 saved_model_for: Callable[[str], str]):
        self._settings = settings
        self._model_settings = model_settings
        self._storage_settings = storage_settings
        self._on_change = on_change
        self._on_model_change = on_model_change
        self._on_storage_change = on_storage_change
        self._saved_model_for = saved_model_for

        top = tk.Toplevel(parent)
        self._top = top
        top.title("TeacherLang 설정")
        top.resizable(False, False)
        top.transient(parent)
        # Stay above the main window even when it is itself always on top. macOS ignores
        # -topmost set before the window is mapped, which left it hidden behind the main window.
        top.bind("<Map>", self._raise_when_mapped)

        self._on_top_var = tk.BooleanVar(value=settings.always_on_top)
        tk.Checkbutton(top, text="항상 위에 표시 (Always on top)", variable=self._on_top_var,
                       command=self._apply).grid(row=0, column=0, columnspan=2, sticky="w",
                                                 padx=16, pady=(16, 8))

        tk.Label(top, text="글자 크기").grid(row=1, column=0, sticky="w", padx=(16, 8))
        self._font_var = tk.StringVar(value=str(settings.font_size))
        font_spin = tk.Spinbox(top, from_=FONT_SIZE_MIN, to=FONT_SIZE_MAX, width=4,
                               textvariable=self._font_var, command=self._apply)
        font_spin.grid(row=1, column=1, sticky="w", padx=(0, 16))
        # Typed values apply on Enter or when focus leaves the field.
        font_spin.bind("<Return>", lambda _event: self._apply())
        font_spin.bind("<FocusOut>", lambda _event: self._apply())

        ttk.Separator(top).grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=12)

        tk.Label(top, text="튜터 제공자").grid(row=3, column=0, sticky="w", padx=(16, 8))
        self._provider_var = tk.StringVar(value=model_settings.provider)
        provider_box = ttk.Combobox(top, textvariable=self._provider_var, state="readonly",
                                    values=list(PROVIDERS), width=12)
        provider_box.grid(row=3, column=1, sticky="w", padx=(0, 16))
        provider_box.bind("<<ComboboxSelected>>", lambda _event: self._change_provider())

        tk.Label(top, text="튜터 모델").grid(row=4, column=0, sticky="w", padx=(16, 8), pady=(6, 0))
        self._model_var = tk.StringVar(value=model_settings.model)
        # Editable, so a full model name can be typed besides the listed aliases.
        self._model_box = ttk.Combobox(top, textvariable=self._model_var, width=24,
                                       values=PROVIDERS[model_settings.provider].model_presets)
        self._model_box.grid(row=4, column=1, sticky="w", padx=(0, 16), pady=(6, 0))
        self._model_box.bind("<<ComboboxSelected>>", lambda _event: self._apply_model())
        self._model_box.bind("<Return>", lambda _event: self._apply_model())
        self._model_box.bind("<FocusOut>", lambda _event: self._apply_model())

        tk.Label(top, text="다음 입력부터 적용 · TEACHERLANG_MODEL 환경변수가 있으면 그 값이 우선",
                 fg="gray55").grid(row=5, column=0, columnspan=2, sticky="w", padx=16, pady=(4, 0))

        ttk.Separator(top).grid(row=6, column=0, columnspan=2, sticky="ew", padx=16, pady=12)

        tk.Label(top, text="기록 보관기간 (일)").grid(row=7, column=0, sticky="w", padx=(16, 8))
        self._retention_var = tk.StringVar(value=str(storage_settings.retention_days))
        retention_spin = tk.Spinbox(top, from_=RETENTION_DAYS_MIN, to=RETENTION_DAYS_MAX, width=4,
                                    textvariable=self._retention_var, command=self._apply_storage)
        retention_spin.grid(row=7, column=1, sticky="w", padx=(0, 16))
        retention_spin.bind("<Return>", lambda _event: self._apply_storage())
        retention_spin.bind("<FocusOut>", lambda _event: self._apply_storage())

        tk.Label(top, text="지난 날짜 기록은 압축 보관 후 기간이 지나면 삭제 · 0이면 삭제 안 함\n"
                           "TEACHERLANG_RETENTION_DAYS 환경변수가 있으면 그 값이 우선",
                 fg="gray55", justify="left").grid(row=8, column=0, columnspan=2, sticky="w",
                                                   padx=16, pady=(4, 0))

        tk.Button(top, text="닫기", command=self.close).grid(row=9, column=0, columnspan=2,
                                                            sticky="e", padx=16, pady=16)
        top.protocol("WM_DELETE_WINDOW", self.close)
        top.bind("<Escape>", lambda _event: self.close())
        top.bind("<Command-w>", lambda _event: self.close())
        self.focus()

    def _raise_when_mapped(self, event: tk.Event) -> None:
        # Child widgets share the toplevel's bindtag; react only to the window itself.
        if event.widget is self._top:
            self._top.attributes("-topmost", True)
            self._top.lift()

    def is_open(self) -> bool:
        return bool(self._top.winfo_exists())

    def focus(self) -> None:
        self._top.lift()
        self._top.focus_force()

    def close(self) -> None:
        # Keep typed values that were not yet confirmed with Enter.
        self._apply()
        self._apply_model()
        self._apply_storage()
        self._top.destroy()

    def _apply(self) -> None:
        try:
            font_size = clamp_font_size(int(self._font_var.get()))
        except ValueError:
            font_size = self._settings.font_size
        self._font_var.set(str(font_size))

        settings = GuiSettings(always_on_top=self._on_top_var.get(), font_size=font_size)
        if settings != self._settings:
            self._settings = settings
            self._on_change(settings)

    def _change_provider(self) -> None:
        provider = self._provider_var.get()
        if provider == self._model_settings.provider:
            return
        self._model_box.configure(values=PROVIDERS[provider].model_presets)
        self._model_var.set(self._saved_model_for(provider))
        self._apply_model()

    def _apply_model(self) -> None:
        model = self._model_var.get().strip()
        if not is_valid_model(model):
            self._top.bell()
            self._model_var.set(self._model_settings.model)
            return
        self._model_var.set(model)

        settings = ModelSettings(provider=self._provider_var.get(), model=model)
        if settings != self._model_settings:
            self._model_settings = settings
            self._on_model_change(settings)

    def _apply_storage(self) -> None:
        try:
            days = clamp_retention_days(int(self._retention_var.get()))
        except ValueError:
            days = self._storage_settings.retention_days
        self._retention_var.set(str(days))

        settings = StorageSettings(retention_days=days)
        if settings != self._storage_settings:
            self._storage_settings = settings
            self._on_storage_change(settings)
