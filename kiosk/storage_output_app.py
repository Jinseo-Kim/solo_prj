"""출력 키오스크 — 세대인 직접 수령 / 로봇 배차.

두 가지 출력 주체:
 · 사람(세대인): PIN/QR 로 인증 → 수령 출력구로 인출
 · 로봇: 배차 버튼 → 서버가 적재 배치(batch)·경로를 계산 → 로봇 출력구로 인출

단독 실행 가능: python storage_output_app.py
"""
from __future__ import annotations

import tkinter as tk
from datetime import datetime

import config
import ui_common as ui
from mqtt_client import MqttClient

KIOSK_ID = "OUTPUT-01"

# 데모 로봇 사양 (실제로는 로봇이 요청 시 보고)
ROBOT_SPEC = {
    "robot_id": "R1",
    "capacity": {"S": 4, "M": 2, "L": 1},
    "max_weight": 30.0,
}


class OutputKiosk:
    def __init__(self, root: tk.Tk, standalone: bool = True):
        self.root = root
        self.standalone = standalone
        self.pending: dict[str, str] = {}   # request_id -> kind(PICKUP/ROBOT)

        root.title(f"보관소 출력 키오스크 · {KIOSK_ID}")
        root.configure(bg=ui.BG)
        root.geometry("640x880")

        self.mqtt = MqttClient(
            KIOSK_ID, online_topic=config.TOPIC_KIOSK_ONLINE.format(kiosk_id=KIOSK_ID)
        )
        self.mqtt.on(config.TOPIC_PICKUP_RES, self._on_pickup_res)
        self.mqtt.on(config.TOPIC_ROBOT_RES, self._on_robot_res)
        self.mqtt.on(config.TOPIC_STATUS, self._on_status)
        self.mqtt.on_connection_change(
            lambda c: self.root.after(0, lambda: self.status.set_connected(c))
        )

        self._build()
        self.mqtt.connect()
        self.show_home()

    # --- 공통 화면 틀 ----------------------------------------------------
    def _build(self):
        self.status = ui.StatusBar(self.root, KIOSK_ID)
        self.status.pack(side="bottom", fill="x")

        self.status_text = tk.Label(self.root, text="", bg=ui.BG, fg=ui.MUTED,
                                    font=(ui.FONT, 12))
        self.status_text.pack(side="bottom", pady=4)

        self.container = tk.Frame(self.root, bg=ui.BG)
        self.container.pack(fill="both", expand=True)

    def _clear(self):
        for w in self.container.winfo_children():
            w.destroy()

    # --- 홈: 주체 선택 ---------------------------------------------------
    def show_home(self):
        self._clear()
        ui.title_label(self.container, "📤 보관소 출력").pack(pady=(40, 6))
        ui.sub_label(self.container, "수령 방식을 선택하세요").pack(pady=(0, 30))

        ui.big_button(self.container, "🙋  직접 수령\n(세대인)", self.show_pickup,
                      bg=ui.ACCENT, width=16, height=4, font_size=22).pack(pady=12)
        ui.big_button(self.container, "🤖  로봇 배차\n(로봇/관리인)", self.show_robot,
                      bg=ui.ACCENT2, width=16, height=4, font_size=22).pack(pady=12)

    # --- 직접 수령 -------------------------------------------------------
    def show_pickup(self):
        self._clear()
        ui.title_label(self.container, "🙋 직접 수령").pack(pady=(24, 4))
        self.pickup_hint = ui.sub_label(self.container, "수령 코드(PIN) 6자리를 입력하세요")
        self.pickup_hint.pack()

        self.code_var = tk.StringVar(value="______")
        tk.Label(self.container, textvariable=self.code_var, bg=ui.PANEL, fg=ui.TEXT,
                 font=(ui.FONT, 40, "bold"), width=10).pack(pady=16)

        self.code = ""
        self.pickup_pad = ui.NumPad(self.container, self._on_code)
        self.pickup_pad.pack(pady=8)

        row = tk.Frame(self.container, bg=ui.BG)
        row.pack(pady=18)
        ui.big_button(row, "QR 스캔", self._qr_scan, bg=ui.PANEL, width=10).pack(side="left", padx=8)
        ui.big_button(row, "인증 ▶", self._submit_pickup, bg=ui.ACCENT2, width=10).pack(side="left", padx=8)
        ui.big_button(row, "뒤로", self.show_home, bg=ui.WARN, width=8).pack(side="left", padx=8)

    def _on_code(self, value: str):
        self.code = value[:6]
        self.code_var.set(self.code.ljust(6, "_"))

    def _qr_scan(self):
        # 실제로는 QR 스캐너 입력. 데모에서는 안내만.
        self.pickup_hint.config(
            text="QR 스캐너에 수령 QR을 보여주세요 (데모: PIN 입력 사용)", fg=ui.MUTED)

    def _submit_pickup(self):
        if len(self.code) < 6:
            self.pickup_hint.config(text="⚠ 6자리를 모두 입력하세요", fg=ui.DANGER)
            return
        if not self.mqtt.connected:
            self.pickup_hint.config(text="⚠ 서버 연결 안 됨", fg=ui.DANGER)
            return
        req_id = self.mqtt.new_request_id()
        self.pending[req_id] = "PICKUP"
        self.mqtt.publish(config.TOPIC_PICKUP_REQ, {
            "type": "PICKUP_REQUEST",
            "request_id": req_id,
            "kiosk_id": KIOSK_ID,
            "auth": {"method": "PIN", "code": self.code},
            "timestamp": datetime.now().astimezone().isoformat(),
        })
        self.pickup_hint.config(text="인증 중…", fg=ui.MUTED)

    def _on_pickup_res(self, msg):
        self.root.after(0, lambda: self._pickup_result(msg))

    def _pickup_result(self, msg):
        if self.pending.pop(msg.get("request_id"), None) != "PICKUP":
            return
        self._clear()
        status = msg.get("status")
        if status == "OK":
            items = msg.get("items", [])
            ui.title_label(self.container, "✅ 인출 완료").pack(pady=(60, 10))
            ui.sub_label(self.container,
                         f"{len(items)}건을 수령 출력구로 꺼내는 중입니다.",
                         color=ui.ACCENT2, size=20).pack(pady=6)
            for it in items:
                ui.sub_label(self.container,
                             f"· {it['dong']}동 {it['ho']}호 [{it['size']}]  {it['slot_id']}"
                             ).pack()
        elif status == "NOT_FOUND":
            self._message("🔍 해당 코드의 물품이 없습니다.", ui.WARN)
        else:
            self._message("⛔ 인증 실패. 코드를 확인하세요.", ui.DANGER)
        ui.big_button(self.container, "처음으로", self.show_home, bg=ui.ACCENT).pack(pady=24)

    # --- 로봇 배차 -------------------------------------------------------
    def show_robot(self):
        self._clear()
        ui.title_label(self.container, "🤖 로봇 배차").pack(pady=(24, 6))
        ui.sub_label(self.container,
                     f"로봇 {ROBOT_SPEC['robot_id']} · 적재칸 "
                     f"S×{ROBOT_SPEC['capacity']['S']} "
                     f"M×{ROBOT_SPEC['capacity']['M']} "
                     f"L×{ROBOT_SPEC['capacity']['L']} · "
                     f"최대 {ROBOT_SPEC['max_weight']}kg").pack(pady=(0, 20))

        self.robot_hint = ui.sub_label(self.container,
                                       "대상 라인을 선택하거나 자동 배차하세요")
        self.robot_hint.pack(pady=6)

        # 대상 선택 (자동 / 특정 동·라인)
        self.target_var = tk.StringVar(value="AUTO")
        opts = [("자동(혼잡도 기반)", "AUTO")]
        for d in config.VALID_DONGS[:3]:
            opts.append((f"{d}동 A라인", f"{d}:A"))
            opts.append((f"{d}동 B라인", f"{d}:B"))
        grid = tk.Frame(self.container, bg=ui.BG)
        grid.pack(pady=10)
        for i, (label, val) in enumerate(opts):
            r, c = divmod(i, 2)
            tk.Radiobutton(
                grid, text=label, value=val, variable=self.target_var,
                indicatoron=False, width=16, height=2, font=(ui.FONT, 14, "bold"),
                fg="white", bg=ui.PANEL, selectcolor=ui.ACCENT2, relief="flat", bd=0,
            ).grid(row=r, column=c, padx=6, pady=6)

        row = tk.Frame(self.container, bg=ui.BG)
        row.pack(pady=20)
        ui.big_button(row, "배차 요청 ▶", self._submit_robot, bg=ui.ACCENT2,
                      width=14).pack(side="left", padx=8)
        ui.big_button(row, "뒤로", self.show_home, bg=ui.WARN, width=8).pack(side="left", padx=8)

    def _submit_robot(self):
        if not self.mqtt.connected:
            self.robot_hint.config(text="⚠ 서버 연결 안 됨", fg=ui.DANGER)
            return
        req_id = self.mqtt.new_request_id()
        self.pending[req_id] = "ROBOT"
        payload = {
            "type": "ROBOT_REQUEST",
            "request_id": req_id,
            "kiosk_id": KIOSK_ID,
            "robot_id": ROBOT_SPEC["robot_id"],
            "capacity": ROBOT_SPEC["capacity"],
            "max_weight": ROBOT_SPEC["max_weight"],
            "timestamp": datetime.now().astimezone().isoformat(),
        }
        tv = self.target_var.get()
        if tv != "AUTO":
            dong, line = tv.split(":")
            payload["target"] = {"dong": int(dong), "line": line}
        self.mqtt.publish(config.TOPIC_ROBOT_REQ, payload)
        self.robot_hint.config(text="배차 계산 중…", fg=ui.MUTED)

    def _on_robot_res(self, msg):
        self.root.after(0, lambda: self._robot_result(msg))

    def _robot_result(self, msg):
        if self.pending.pop(msg.get("request_id"), None) != "ROBOT":
            return
        self._clear()
        status = msg.get("status")
        if status == "OK":
            batch = msg.get("batch", [])
            tgt = msg.get("target", {})
            ui.title_label(self.container, "✅ 배차 완료").pack(pady=(20, 6))
            ui.sub_label(self.container,
                         f"대상: {tgt.get('dong')}동 {tgt.get('line')}라인 · "
                         f"{len(batch)}건 · {msg.get('load_weight')}kg",
                         color=ui.ACCENT2, size=18).pack(pady=4)
            ui.sub_label(self.container,
                         f"배송 경로(SCAN): {' → '.join(str(h) for h in msg.get('route', []))}호"
                         ).pack(pady=(0, 10))
            box = tk.Frame(self.container, bg=ui.PANEL)
            box.pack(fill="x", padx=24, pady=6)
            for it in batch:
                tk.Label(box,
                         text=f"칸 {it.get('compartment')} ← {it['dong']}동 {it['ho']}호 "
                              f"[{it['size']}]  {it['slot_id']}",
                         bg=ui.PANEL, fg=ui.TEXT, font=(ui.FONT, 14),
                         anchor="w").pack(fill="x", padx=12, pady=3)
        elif status == "EMPTY":
            self._message("📭 배송 대기 물품이 없습니다.", ui.WARN)
        else:
            self._message("⏳ 로봇이 사용 중입니다. 잠시 후 다시 시도하세요.", ui.WARN)
        ui.big_button(self.container, "처음으로", self.show_home, bg=ui.ACCENT).pack(pady=24)

    # --- 공통 ------------------------------------------------------------
    def _message(self, text, color):
        ui.title_label(self.container, "").pack(pady=20)
        ui.sub_label(self.container, text, color=color, size=22).pack(pady=40)

    def _on_status(self, msg):
        occ = msg.get("occupancy", {})
        wait = msg.get("waiting", {})
        txt = (f"보관소 점유율  S {occ.get('S',0):.0%}  M {occ.get('M',0):.0%}  "
               f"L {occ.get('L',0):.0%}   |   대기 DOOR {wait.get('DOOR',0)} · "
               f"PICKUP {wait.get('PICKUP',0)}")
        self.root.after(0, lambda: self.status_text.config(text=txt))

    def close(self):
        self.mqtt.disconnect()


def main():
    root = tk.Tk()
    app = OutputKiosk(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.close(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
