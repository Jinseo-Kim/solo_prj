"""키오스크 공통 UI 요소 (Tkinter).

큰 버튼, 숫자 패드, 상태바 등 입력/출력 키오스크가 공유하는 위젯.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable

# 색상 테마
BG = "#0f1724"
PANEL = "#1b2537"
ACCENT = "#2f81f7"
ACCENT2 = "#2ea043"
WARN = "#d29922"
DANGER = "#f85149"
TEXT = "#e6edf3"
MUTED = "#8b98a9"

FONT = "Helvetica"


def big_button(parent, text, command, bg=ACCENT, width=14, height=2, font_size=20):
    return tk.Button(
        parent, text=text, command=command,
        bg=bg, fg="white", activebackground=bg, activeforeground="white",
        font=(FONT, font_size, "bold"), width=width, height=height,
        relief="flat", bd=0, cursor="hand2",
    )


def title_label(parent, text):
    return tk.Label(parent, text=text, bg=BG, fg=TEXT, font=(FONT, 30, "bold"))


def sub_label(parent, text, color=MUTED, size=16):
    return tk.Label(parent, text=text, bg=BG, fg=color, font=(FONT, size))


class StatusBar(tk.Frame):
    """하단 연결 상태 표시줄."""

    def __init__(self, parent, kiosk_id: str):
        super().__init__(parent, bg=PANEL, height=40)
        self.kiosk_id = kiosk_id
        self._dot = tk.Label(self, text="●", bg=PANEL, fg=DANGER, font=(FONT, 14))
        self._dot.pack(side="left", padx=(16, 6))
        self._text = tk.Label(self, text="서버 연결 안 됨", bg=PANEL, fg=MUTED,
                              font=(FONT, 12))
        self._text.pack(side="left")
        tk.Label(self, text=kiosk_id, bg=PANEL, fg=MUTED,
                 font=(FONT, 12)).pack(side="right", padx=16)

    def set_connected(self, connected: bool):
        self._dot.config(fg=ACCENT2 if connected else DANGER)
        self._text.config(text="서버 연결됨" if connected else "서버 연결 안 됨")


class NumPad(tk.Frame):
    """키오스크용 숫자 입력 패드. on_change(value:str) 콜백 호출."""

    def __init__(self, parent, on_change: Callable[[str], None]):
        super().__init__(parent, bg=BG)
        self.on_change = on_change
        self.value = ""
        keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "지움", "0", "←"]
        for i, k in enumerate(keys):
            r, c = divmod(i, 3)
            bg = WARN if k in ("지움", "←") else PANEL
            b = tk.Button(self, text=k, font=(FONT, 22, "bold"),
                          bg=bg, fg="white", activebackground=bg,
                          width=5, height=2, relief="flat", bd=0, cursor="hand2",
                          command=lambda key=k: self._press(key))
            b.grid(row=r, column=c, padx=6, pady=6)

    def _press(self, key: str):
        if key == "지움":
            self.value = ""
        elif key == "←":
            self.value = self.value[:-1]
        else:
            self.value += key
        self.on_change(self.value)

    def clear(self):
        self.value = ""
        self.on_change(self.value)
