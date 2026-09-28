"""Asks in a dialog to install the Claude Code hook when the GUI starts and finds it missing.

A dialog instead of the terminal: the GUI usually runs as a background job (`teacherlang-gui &`).
"""

import tkinter as tk
from tkinter import messagebox

from .install import INSTALL_SCRIPT, InstallError
from .startup_install import apply_pending_install, find_pending_install

DIALOG_TITLE = "TeacherLang"


def offer_install_in_dialog(root: tk.Tk) -> None:
    try:
        pending = find_pending_install()
        if pending is None:
            return
        wants_install = messagebox.askyesno(
            DIALOG_TITLE, "Claude Code hook이 설치되어 있지 않습니다. 지금 설치할까요?",
            detail=f"{pending.path} 변경 내용 (기존 파일은 백업):\n\n{pending.diff}", parent=root)
        if not wants_install:
            return
        backup = apply_pending_install(pending)
    except (InstallError, OSError) as exc:
        messagebox.showwarning(DIALOG_TITLE, "Claude Code hook을 설치하지 못했습니다.",
                               detail=f"{exc}\n\n직접 설치: {INSTALL_SCRIPT}", parent=root)
        return
    backup_line = f"\n백업: {backup}" if backup else ""
    messagebox.showinfo(DIALOG_TITLE, "Claude Code hook을 설치했습니다.",
                        detail=f"실행 중인 Claude Code 세션은 재시작하세요.{backup_line}",
                        parent=root)
