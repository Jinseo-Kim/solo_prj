"""모의 보관소 서버 (시뮬레이션 스텁).

실제 시뮬레이션/보관소 제어기를 붙이기 전까지, 키오스크를 단독으로
테스트할 수 있도록 서버 역할을 대신한다. 설계 문서의 알고리즘을
단순화해 구현했다:

 · 입력: 동·호수 검증 → 수령옵션 결정(DOOR/PICKUP) → 체류시간 기반 띠(B1/B2/B3)
         배정 → 출력구 최근접 Best-fit 셀 선택
 · 수령: PIN/QR 매칭 → 인출
 · 로봇: 우선순위(대기시간)+층 묶음 보너스로 batch 선택 → Best-fit 적재칸
         → SCAN 경로 계산

콘솔 로그로 처리 내역을 보여준다.
실행: python mock_server.py
"""
from __future__ import annotations

import itertools
import json
import random
import signal
import threading
import time
from datetime import datetime, timedelta

import paho.mqtt.client as mqtt

import config
from models import Item, Slot

# 띠별 셀 생성 수 (크기별). 데모 규모.
SLOTS_PER_BAND_SIZE = {"S": 20, "M": 16, "L": 8}
BANDS = ("B1", "B2", "B3")   # Hot / Warm / Cold


class LockerServer:
    def __init__(self):
        self.slots: list[Slot] = self._build_slots()
        self.items: dict[str, Item] = {}
        self._id_seq = itertools.count(1)
        self.robot_busy = False
        self.lock = threading.Lock()

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="locker-server")
        if config.BROKER_USERNAME:
            self.client.username_pw_set(config.BROKER_USERNAME, config.BROKER_PASSWORD)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    # --- 셀 생성: 띠 = 출력구와의 거리 ----------------------------------
    def _build_slots(self) -> list[Slot]:
        slots = []
        for band in BANDS:
            for size, n in SLOTS_PER_BAND_SIZE.items():
                for col in range(n):
                    level = {"L": 1, "M": 2, "S": 3}[size]  # 하단 L, 중단 M, 상단 S
                    slots.append(Slot(
                        id=f"{band}-{size}{col:02d}-L{level}",
                        size=size, band=band, col=col, level=level,
                    ))
        return slots

    # --- MQTT 수명주기 ---------------------------------------------------
    def start(self):
        # connect_async + loop_start: 브로커가 아직 없어도 예외 없이 자동 재시도
        self.client.connect_async(config.BROKER_HOST, config.BROKER_PORT, config.BROKER_KEEPALIVE)
        self.client.loop_start()
        threading.Thread(target=self._status_loop, daemon=True).start()
        print(f"[서버] MQTT {config.BROKER_HOST}:{config.BROKER_PORT} 연결 시도… "
              f"(브로커가 없으면 자동 재시도)")

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if not reason_code.is_failure:
            for t in (config.TOPIC_INPUT_REQ, config.TOPIC_PICKUP_REQ, config.TOPIC_ROBOT_REQ):
                client.subscribe(t, qos=config.QOS)
            print("[서버] 연결 완료. 요청 대기 중…")
        else:
            print(f"[서버] 연결 실패: {reason_code}")

    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except ValueError:
            return
        if msg.topic == config.TOPIC_INPUT_REQ:
            self._handle_input(data)
        elif msg.topic == config.TOPIC_PICKUP_REQ:
            self._handle_pickup(data)
        elif msg.topic == config.TOPIC_ROBOT_REQ:
            self._handle_robot(data)

    def _reply(self, topic, payload):
        self.client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=config.QOS)

    # --- 입력 처리 -------------------------------------------------------
    def _handle_input(self, req: dict):
        rid = req.get("request_id")
        dong, ho, size = req.get("dong"), req.get("ho"), req.get("size")
        weight = req.get("weight", 0.0)
        ok, floor, line, reason = config.parse_unit(dong, ho)

        if not ok:
            print(f"[입력] 거부 {dong}-{ho}: {reason}")
            return self._reply(config.TOPIC_INPUT_RES, {
                "type": "INPUT_RESPONSE", "request_id": rid,
                "status": "REJECT", "message": reason,
            })

        if weight > config.SIZE_MAX_WEIGHT.get(size, 999):
            msg = f"{size} 입력구 허용 무게 초과({weight}kg). 더 큰 입력구를 사용하세요."
            print(f"[입력] 거부 {dong}-{ho}: {msg}")
            return self._reply(config.TOPIC_INPUT_RES, {
                "type": "INPUT_RESPONSE", "request_id": rid,
                "status": "REJECT", "message": msg,
            })

        # 수령 옵션 (실제로는 세대 설정 조회). 데모: 70% DOOR, 30% PICKUP.
        option = "PICKUP" if random.random() < 0.3 else "DOOR"
        band = self._target_band(option)
        slot = self._place(item_size=size, band=band)

        if slot is None:
            print(f"[입력] 포화: {size} 셀 없음")
            return self._reply(config.TOPIC_INPUT_RES, {
                "type": "INPUT_RESPONSE", "request_id": rid,
                "status": "OVERFLOW",
                "message": "보관소 포화. 관리실에 보관해 주세요.",
            })

        with self.lock:
            item_id = f"PKG-{next(self._id_seq):04d}"
            pickup_code = f"{random.randint(0, 999999):06d}" if option == "PICKUP" else None
            eta = self._estimate_eta(option)
            item = Item(id=item_id, dong=dong, ho=ho, floor=floor, line=line,
                        size=size, weight=weight, option=option, slot_id=slot.id,
                        pickup_code=pickup_code, eta=eta)
            slot.occupied = True
            slot.item_id = item_id
            self.items[item_id] = item

        print(f"[입력] {item_id} {dong}동 {ho}호 [{size}] {weight}kg "
              f"→ {slot.id} ({band}, {option})")
        self._reply(config.TOPIC_INPUT_RES, {
            "type": "INPUT_RESPONSE", "request_id": rid, "status": "OK",
            "slot_id": slot.id, "input_port": size, "option": option,
            "pickup_code": pickup_code, "eta": eta,
            "message": f"{size} 입력구에 올려주세요. 적재 위치 {slot.id}.",
        })

    @staticmethod
    def _target_band(option: str) -> str:
        # 단순화: 문앞 배송 임박 → B1(Hot), 직접 수령(저녁) → B2(Warm)
        return "B1" if option == "DOOR" else "B2"

    def _place(self, item_size: str, band: str) -> Slot | None:
        """Best-fit: 지정 띠에서 같은 크기 빈 셀 우선, 없으면 바깥 띠 → 큰 셀."""
        order = {"B1": ["B1", "B2", "B3"], "B2": ["B2", "B3", "B1"],
                 "B3": ["B3", "B2", "B1"]}[band]
        want = config.SIZE_RANK[item_size]
        for b in order:
            cands = [s for s in self.slots if s.band == b and not s.occupied
                     and config.SIZE_RANK[s.size] >= want]
            if cands:
                # 크기 낭비 최소 → 출력구 근접(col 작을수록 가깝다고 가정)
                cands.sort(key=lambda s: (config.SIZE_RANK[s.size] - want, s.col))
                return cands[0]
        return None

    @staticmethod
    def _estimate_eta(option: str) -> str:
        now = datetime.now().astimezone()
        delta = timedelta(hours=1) if option == "DOOR" else timedelta(hours=5)
        return (now + delta).replace(microsecond=0).isoformat()

    # --- 수령 처리 -------------------------------------------------------
    def _handle_pickup(self, req: dict):
        rid = req.get("request_id")
        code = (req.get("auth") or {}).get("code", "")
        with self.lock:
            matched = [it for it in self.items.values()
                       if it.status == "STORED" and it.option == "PICKUP"
                       and it.pickup_code == code]
            for it in matched:
                it.status = "PICKED"
                self._free_slot(it.slot_id)

        if not matched:
            print(f"[수령] 코드 {code}: 해당 없음")
            return self._reply(config.TOPIC_PICKUP_RES, {
                "type": "PICKUP_RESPONSE", "request_id": rid,
                "status": "NOT_FOUND", "items": [],
                "message": "해당 코드의 보관 물품이 없습니다.",
            })

        print(f"[수령] 코드 {code}: {len(matched)}건 인출")
        self._reply(config.TOPIC_PICKUP_RES, {
            "type": "PICKUP_RESPONSE", "request_id": rid, "status": "OK",
            "out_port": "PICKUP",
            "items": [{"id": it.id, "dong": it.dong, "ho": it.ho,
                       "size": it.size, "slot_id": it.slot_id} for it in matched],
            "message": f"수령 출력구로 {len(matched)}건 인출 중입니다.",
        })

    # --- 로봇 배차 -------------------------------------------------------
    def _handle_robot(self, req: dict):
        rid = req.get("request_id")
        if self.robot_busy:
            return self._reply(config.TOPIC_ROBOT_RES, {
                "type": "ROBOT_RESPONSE", "request_id": rid, "status": "BUSY",
                "message": "로봇 사용 중",
            })

        cap = req.get("capacity", {"S": 4, "M": 2, "L": 1})
        max_weight = req.get("max_weight", 30.0)
        target = req.get("target")

        with self.lock:
            # 배송 대기(DOOR) 물품 풀
            pool = [it for it in self.items.values()
                    if it.status == "STORED" and it.option == "DOOR"]
            if target:
                pool = [it for it in pool
                        if it.dong == target["dong"] and it.line == target["line"]]
            elif pool:
                # 자동: 가장 많이 밀린 (동,라인) 선택
                groups: dict[tuple, int] = {}
                for it in pool:
                    groups[(it.dong, it.line)] = groups.get((it.dong, it.line), 0) + 1
                best = max(groups, key=groups.get)
                target = {"dong": best[0], "line": best[1]}
                pool = [it for it in pool
                        if it.dong == target["dong"] and it.line == target["line"]]

            batch = self._select_batch(pool, cap, max_weight)
            for it, _ in batch:
                it.status = "DISPATCHED"
                self._free_slot(it.slot_id)

        if not batch:
            return self._reply(config.TOPIC_ROBOT_RES, {
                "type": "ROBOT_RESPONSE", "request_id": rid, "status": "EMPTY",
                "target": target or {}, "batch": [],
                "message": "배송 대기 물품이 없습니다.",
            })

        # SCAN 경로: 층 오름차순, 같은 층은 호수 오름차순
        route = sorted({it.ho for it, _ in batch})
        load_w = round(sum(it.weight for it, _ in batch), 1)
        print(f"[로봇] {target['dong']}동 {target['line']}라인 "
              f"{len(batch)}건 배차, {load_w}kg, 경로 {route}")
        self._reply(config.TOPIC_ROBOT_RES, {
            "type": "ROBOT_RESPONSE", "request_id": rid, "status": "OK",
            "robot_id": req.get("robot_id"), "target": target,
            "batch": [{"id": it.id, "dong": it.dong, "ho": it.ho, "floor": it.floor,
                       "size": it.size, "slot_id": it.slot_id, "compartment": comp}
                      for it, comp in batch],
            "route": route, "load_weight": load_w, "out_port": "ROBOT",
            "message": f"{len(batch)}건 적재. SCAN 경로로 배송하세요.",
        })

    @staticmethod
    def _select_batch(pool, cap, max_weight):
        """우선순위(대기시간)+층 묶음 보너스 → Best-fit 적재칸."""
        free = {"S": cap.get("S", 0), "M": cap.get("M", 0), "L": cap.get("L", 0)}
        bigger = {"S": ["S", "M", "L"], "M": ["M", "L"], "L": ["L"]}
        chosen, floors, weight = [], set(), 0.0

        def wait_sec(it):
            return (datetime.now() - datetime.fromisoformat(it.arrived_at)).total_seconds()

        remaining = list(pool)
        while remaining:
            remaining.sort(key=lambda it: -(wait_sec(it) + (3600 if it.floor in floors else 0)))
            it = remaining.pop(0)
            # 들어가는 가장 작은 빈 칸
            comp_size = next((s for s in bigger[it.size] if free[s] > 0), None)
            if comp_size is None or weight + it.weight > max_weight:
                continue
            free[comp_size] -= 1
            idx = cap[comp_size] - free[comp_size]
            chosen.append((it, f"{comp_size}{idx}"))
            floors.add(it.floor)
            weight += it.weight
        return chosen

    # --- 보조 -----------------------------------------------------------
    def _free_slot(self, slot_id: str | None):
        for s in self.slots:
            if s.id == slot_id:
                s.occupied = False
                s.item_id = None
                return

    def _status_loop(self):
        while True:
            time.sleep(5)
            if not self.client.is_connected():
                continue
            self._reply_status()

    def _reply_status(self):
        occ = {}
        for size in config.SIZES:
            size_slots = [s for s in self.slots if s.size == size]
            used = sum(1 for s in size_slots if s.occupied)
            occ[size] = round(used / len(size_slots), 2) if size_slots else 0
        stored = [it for it in self.items.values() if it.status == "STORED"]
        waiting = {
            "DOOR": sum(1 for it in stored if it.option == "DOOR"),
            "PICKUP": sum(1 for it in stored if it.option == "PICKUP"),
        }
        self.client.publish(config.TOPIC_STATUS, json.dumps({
            "type": "STATUS",
            "timestamp": datetime.now().astimezone().isoformat(),
            "occupancy": occ, "waiting": waiting,
        }, ensure_ascii=False), qos=config.QOS, retain=True)


def main():
    server = LockerServer()
    server.start()
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    print("[서버] 종료하려면 Ctrl+C")
    try:
        stop.wait()
    finally:
        server.stop()
        print("\n[서버] 종료")


if __name__ == "__main__":
    main()
