"""보관소 키오스크 런처.

실행 모드를 선택한다.
  python main.py            → 모드 선택 화면
  python main.py input      → 입력 키오스크 바로 실행
  python main.py output     → 출력 키오스크 바로 실행
"""
from __future__ import annotations

import sys
import tkinter as tk

import ui_common as ui


def launch(mode: str):
    if mode == "input":
        from storage_input_app import main as run
    elif mode == "output":
        from storage_output_app import main as run
    else:
        raise SystemExit(f"알 수 없는 모드: {mode} (input | output)")
    run()


def chooser():
    root = tk.Tk()
    root.title("보관소 키오스크 — 모드 선택")
    root.configure(bg=ui.BG)
    root.geometry("520x420")

    ui.title_label(root, "🏢 보관소 키오스크").pack(pady=(50, 8))
    ui.sub_label(root, "실행할 모드를 선택하세요").pack(pady=(0, 30))

    def go(mode):
        root.destroy()
        launch(mode)

    ui.big_button(root, "📦 입력 (택배기사)", lambda: go("input"),
                  bg=ui.ACCENT, width=22, height=3, font_size=20).pack(pady=10)
    ui.big_button(root, "📤 출력 (사람 / 로봇)", lambda: go("output"),
                  bg=ui.ACCENT2, width=22, height=3, font_size=20).pack(pady=10)

    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        launch(sys.argv[1].lower())
    else:
        chooser()
