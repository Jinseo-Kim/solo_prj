"""입력 키오스크 — 택배기사용.

흐름:
 1) 동 입력 → 2) 호수 입력 → 3) 크기(S/M/L) 선택 → 4) 무게 측정(센서 대체: 수동/모의)
 5) 서버로 INPUT_REQUEST 발행 → 응답에 따라 적재 위치/입력구/수령코드 안내

서버 응답은 locker/input/response 로 수신한다.
단독 실행 가능: python storage_input_app.py
"""
from __future__ import annotations

import random
import tkinter as tk
from datetime import datetime

import config
import ui_common as ui
from mqtt_client import MqttClient

KIOSK_ID = "INPUT-01"


class InputKiosk:
    def __init__(self, root: tk.Tk, standalone: bool = True):
        self.root = root
        self.standalone = standalone
        self.pending: dict[str, dict] = {}   # request_id -> 접수 데이터

        root.title(f"보관소 입력 키오스크 · {KIOSK_ID}")
        root.configure(bg=ui.BG)
        root.geometry("640x880")

        self.mqtt = MqttClient(
            KIOSK_ID, online_topic=config.TOPIC_KIOSK_ONLINE.format(kiosk_id=KIOSK_ID)
        )
        self.mqtt.on(config.TOPIC_INPUT_RES, self._on_response)
        self.mqtt.on_connection_change(
            lambda c: self.root.after(0, lambda: self.status.set_connected(c))
        )

        self._build()
        self.mqtt.connect()
        self.reset()

    # --- 화면 구성 -------------------------------------------------------
    def _build(self):
        self.status = ui.StatusBar(self.root, KIOSK_ID)
        self.status.pack(side="bottom", fill="x")

        ui.title_label(self.root, "📦 택배 접수").pack(pady=(24, 4))
        self.hint = ui.sub_label(self.root, "동을 입력하세요")
        self.hint.pack()

        # 입력 표시
        disp = tk.Frame(self.root, bg=ui.BG)
        disp.pack(pady=14)
        self.dong_var = tk.StringVar(value="―")
        self.ho_var = tk.StringVar(value="―")
        self._field(disp, "동", self.dong_var, 0)
        self._field(disp, "호", self.ho_var, 1)

        # 숫자 패드
        self.pad = ui.NumPad(self.root, self._on_pad)
        self.pad.pack(pady=8)

        # 크기 선택
        self.size_frame = tk.Frame(self.root, bg=ui.BG)
        self.size_var = tk.StringVar(value="")
        for i, s in enumerate(config.SIZES):
            tk.Radiobutton(
                self.size_frame, text=config.SIZE_LABEL[s], value=s,
                variable=self.size_var, indicatoron=False, width=12, height=2,
                font=(ui.FONT, 16, "bold"), fg="white", bg=ui.PANEL,
                selectcolor=ui.ACCENT, relief="flat", bd=0,
                command=self._refresh_buttons,
            ).grid(row=0, column=i, padx=6)

        # 하단 조작 버튼
        self.btns = tk.Frame(self.root, bg=ui.BG)
        self.btns.pack(pady=16)
        self.next_btn = ui.big_button(self.btns, "다음 ▶", self._next, bg=ui.ACCENT)
        self.submit_btn = ui.big_button(self.btns, "접수하기", self._submit, bg=ui.ACCENT2)
        self.cancel_btn = ui.big_button(self.btns, "처음으로", self.reset, bg=ui.WARN,
                                        width=10)

        # 결과 패널
        self.result = tk.Label(self.root, text="", bg=ui.PANEL, fg=ui.TEXT,
                               font=(ui.FONT, 16), wraplength=560, justify="left",
                               height=5)

    def _field(self, parent, label, var, col):
        f = tk.Frame(parent, bg=ui.PANEL, width=180, height=90)
        f.grid(row=0, column=col, padx=12)
        f.pack_propagate(False)
        tk.Label(f, text=label, bg=ui.PANEL, fg=ui.MUTED,
                 font=(ui.FONT, 13)).pack(pady=(10, 0))
        tk.Label(f, textvariable=var, bg=ui.PANEL, fg=ui.TEXT,
                 font=(ui.FONT, 30, "bold")).pack()

    # --- 단계 관리 -------------------------------------------------------
    def reset(self):
        self.step = "dong"
        self.dong = ""
        self.ho = ""
        self.dong_var.set("―")
        self.ho_var.set("―")
        self.size_var.set("")
        self.pad.clear()
        self.hint.config(text="동을 입력하세요", fg=ui.MUTED)
        self.size_frame.pack_forget()
        self.result.pack_forget()
        self._refresh_buttons()

    def _on_pad(self, value: str):
        if self.step == "dong":
            self.dong = value
            self.dong_var.set(value or "―")
        elif self.step == "ho":
            self.ho = value
            self.ho_var.set(value or "―")
        self._refresh_buttons()

    def _next(self):
        if self.step == "dong":
            if not self.dong:
                return
            self.step = "ho"
            self.pad.clear()
            self.hint.config(text="호수를 입력하세요 (예: 1502)")
        elif self.step == "ho":
            if not self.ho:
                return
            # 동·호수 검증
            ok, floor, line, reason = config.parse_unit(int(self.dong), int(self.ho))
            if not ok:
                self.hint.config(text=f"⚠ {reason}", fg=ui.DANGER)
                return
            self.step = "size"
            self.hint.config(text="물품 크기를 선택하세요", fg=ui.MUTED)
            self.pad.pack_forget()
            self.size_frame.pack(pady=10)
        self._refresh_buttons()

    def _refresh_buttons(self):
        self.next_btn.pack_forget()
        self.submit_btn.pack_forget()
        self.cancel_btn.pack_forget()
        if self.step in ("dong", "ho"):
            self.next_btn.pack(side="left", padx=8)
        elif self.step == "size":
            self.submit_btn.pack(side="left", padx=8)
        self.cancel_btn.pack(side="left", padx=8)

    # --- 접수(발행) ------------------------------------------------------
    def _submit(self):
        if not self.size_var.get():
            self.hint.config(text="⚠ 크기를 선택하세요", fg=ui.DANGER)
            return
        if not self.mqtt.connected:
            self.hint.config(text="⚠ 서버에 연결되지 않았습니다", fg=ui.DANGER)
            return
        size = self.size_var.get()
        # 무게: 실제로는 저울 센서 값. 여기서는 크기대별 모의 측정.
        weight = self._measure_weight(size)
        req_id = self.mqtt.new_request_id()
        payload = {
            "type": "INPUT_REQUEST",
            "request_id": req_id,
            "kiosk_id": KIOSK_ID,
            "dong": int(self.dong),
            "ho": int(self.ho),
            "size": size,
            "weight": weight,
            "timestamp": datetime.now().astimezone().isoformat(),
        }
        self.pending[req_id] = payload
        self.mqtt.publish(config.TOPIC_INPUT_REQ, payload)
        self.hint.config(text=f"접수 중… (무게 {weight}kg) 서버 응답 대기", fg=ui.MUTED)
        self.submit_btn.config(state="disabled")

    @staticmethod
    def _measure_weight(size: str) -> float:
        base = {"S": (0.3, 4.0), "M": (1.0, 12.0), "L": (3.0, 25.0)}[size]
        return round(random.uniform(*base), 1)

    def _on_response(self, msg: dict):
        # MQTT 스레드 → Tkinter 스레드로 넘김
        self.root.after(0, lambda: self._show_result(msg))

    def _show_result(self, msg: dict):
        self.submit_btn.config(state="normal")
        req_id = msg.get("request_id")
        if req_id and req_id not in self.pending:
            return  # 다른 키오스크의 응답
        self.pending.pop(req_id, None)

        status = msg.get("status")
        if status == "OK":
            lines = [
                f"✅ 접수 완료 — {msg.get('input_port')} 입력구에 올려주세요.",
                f"적재 위치: {msg.get('slot_id')}",
                f"수령 방식: {'문앞 배송(DOOR)' if msg.get('option') == 'DOOR' else '직접 수령(PICKUP)'}",
            ]
            if msg.get("pickup_code"):
                lines.append(f"수령 코드: {msg['pickup_code']} (세대 앱으로도 전송됨)")
            if msg.get("eta"):
                lines.append(f"예상 출고: {msg['eta']}")
            self._result_panel("\n".join(lines), ui.ACCENT2)
        elif status == "OVERFLOW":
            self._result_panel(
                "⚠ 해당 크기 셀이 가득 찼습니다.\n" + msg.get("message", "관리실에 보관해 주세요."),
                ui.WARN)
        else:  # REJECT 등
            self._result_panel("⛔ 접수 거부\n" + msg.get("message", "다시 확인해 주세요."),
                               ui.DANGER)

    def _result_panel(self, text: str, color: str):
        self.result.config(text=text, fg=color)
        self.result.pack(fill="x", padx=24, pady=10)
        # 5초 뒤 자동 초기화
        self.root.after(5000, self.reset)

    def close(self):
        self.mqtt.disconnect()


def main():
    root = tk.Tk()
    app = InputKiosk(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.close(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
