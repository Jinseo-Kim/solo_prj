# 보관소 키오스크 ↔ 서버 MQTT 프로토콜 명세

모든 메시지는 **JSON (UTF-8)** 이며 QoS 1 로 발행한다.
`broker` 는 내부 서버(기본 `localhost:1883`)이다.

## 1. 토픽 구조

| 방향 | 토픽 | 발행자 | 설명 |
|---|---|---|---|
| 요청 | `locker/input/request` | 입력 키오스크 | 택배 접수(동·호수·크기·무게) |
| 응답 | `locker/input/response` | 서버(보관소) | 셀 배정 결과 |
| 요청 | `locker/output/pickup/request` | 출력 키오스크 | 세대인 직접 수령(PIN/QR) |
| 응답 | `locker/output/pickup/response` | 서버 | 인증·인출 결과 |
| 요청 | `locker/output/robot/request` | 출력 키오스크/로봇 | 로봇 배차·적재 요청 |
| 응답 | `locker/output/robot/response` | 서버 | 적재 배치(batch) 결과 |
| 상태 | `locker/status` | 서버 | 보관소 점유율·웨이브 등 브로드캐스트(retained) |
| 생존 | `locker/kiosk/<id>/online` | 키오스크 | LWT 로 online/offline |

모든 요청 메시지는 고유 `request_id` 를 포함하고, 응답은 같은 `request_id` 를 되돌려준다.

## 2. 메시지 스키마

### 2.1 입력 요청 — `locker/input/request`
```json
{
  "type": "INPUT_REQUEST",
  "request_id": "a1b2c3",
  "kiosk_id": "INPUT-01",
  "dong": 101,
  "ho": 1502,
  "size": "M",
  "weight": 2.3,
  "timestamp": "2026-10-31T14:05:00+09:00"
}
```
`size` ∈ `S | M | L`, `weight` 단위 kg.

### 2.2 입력 응답 — `locker/input/response`
```json
{
  "type": "INPUT_RESPONSE",
  "request_id": "a1b2c3",
  "status": "OK",
  "slot_id": "B1-C03-L2",
  "input_port": "M",
  "option": "PICKUP",
  "pickup_code": "472913",
  "eta": "2026-10-31T19:00:00+09:00",
  "message": "M 입력구에 올려주세요. 적재 위치 B1-C03-L2."
}
```
`status` ∈ `OK | REJECT | OVERFLOW`
- `REJECT`: 존재하지 않는 동·호수 또는 입력구보다 큰 물품
- `OVERFLOW`: 맞는 셀 없음(버퍼/관리실 안내)
- `pickup_code`: `option == "PICKUP"` 일 때만 발급

### 2.3 수령 요청 — `locker/output/pickup/request`
```json
{
  "type": "PICKUP_REQUEST",
  "request_id": "d4e5f6",
  "kiosk_id": "OUTPUT-01",
  "auth": { "method": "PIN", "code": "472913" },
  "timestamp": "2026-10-31T19:12:00+09:00"
}
```
`auth.method` ∈ `PIN | QR`

### 2.4 수령 응답 — `locker/output/pickup/response`
```json
{
  "type": "PICKUP_RESPONSE",
  "request_id": "d4e5f6",
  "status": "OK",
  "items": [
    { "id": "PKG-0007", "dong": 101, "ho": 1502, "size": "M", "slot_id": "B1-C03-L2" }
  ],
  "out_port": "PICKUP",
  "message": "수령 출력구로 2건 인출 중입니다."
}
```
`status` ∈ `OK | NOT_FOUND | DENIED`

### 2.5 로봇 배차 요청 — `locker/output/robot/request`
```json
{
  "type": "ROBOT_REQUEST",
  "request_id": "77aa88",
  "kiosk_id": "OUTPUT-01",
  "robot_id": "R1",
  "capacity": { "S": 4, "M": 2, "L": 1 },
  "max_weight": 30.0,
  "target": { "dong": 101, "line": "A" },
  "timestamp": "2026-10-31T14:30:00+09:00"
}
```
`target` 생략 시 서버가 혼잡도 기반으로 최우선 (동,라인) 을 선택한다.

### 2.6 로봇 배차 응답 — `locker/output/robot/response`
```json
{
  "type": "ROBOT_RESPONSE",
  "request_id": "77aa88",
  "status": "OK",
  "robot_id": "R1",
  "target": { "dong": 101, "line": "A" },
  "batch": [
    { "id": "PKG-0007", "dong": 101, "ho": 1502, "floor": 15, "size": "M",
      "slot_id": "B1-C03-L2", "compartment": "M1" }
  ],
  "route": [1502, 1203, 901],
  "load_weight": 6.8,
  "out_port": "ROBOT",
  "message": "3건 적재. SCAN 경로로 배송하세요."
}
```
`status` ∈ `OK | EMPTY | BUSY`

### 2.7 상태 브로드캐스트 — `locker/status` (retained)
```json
{
  "type": "STATUS",
  "timestamp": "2026-10-31T14:30:05+09:00",
  "occupancy": { "S": 0.42, "M": 0.55, "L": 0.30 },
  "waiting": { "DOOR": 18, "PICKUP": 7 },
  "bands": { "B1": 0.6, "B2": 0.45, "B3": 0.3 }
}
```
