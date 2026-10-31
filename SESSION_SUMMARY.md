# LastGate 보관소 시스템 — 세션 정리 및 결과물 명세

> 최종 갱신 2026-10-31 · 아파트 단지용 로봇 택배 보관소의 **보관소 서버**, **웹 입력·출력 키오스크**, **세대 웹**을 만든 과정과 결과물 파일을 정리한 문서입니다.
> 프로젝트 위치: `~/2026_makerton` (iCloud 동기화 문제로 Desktop에서 옮김, git 저장소 아님)
> 설치·실행 방법은 [README.md](README.md), MQTT 메시지 규격은 [protocol.md](protocol.md), 세대 웹 상세는 [end_user_wep/README.md](end_user_wep/README.md)가 기준 문서입니다.

---

## 1. 한눈에 보기

| 항목 | 최종 결과 |
|---|---|
| 구성 | 보관소 서버(Python) + 웹 입력·출력 키오스크(React) + 세대 웹(Node 중계 서버 + 기존 화면) + Mosquitto 브로커 + FMS 대역(테스트용) |
| 통신 | 내부 서버 MQTT. 서버·FMS·세대 웹 서버는 TCP 1883, 브라우저 키오스크는 WebSocket 9001, 입주민 휴대폰은 세대 웹 서버에 HTTP |
| 저장 | SQLite `server/data/locker.db` (데이터는 보관소 서버 한 곳에만 있음) |
| 보관소 | 하드웨어·보관소 시뮬레이터 없이 서버 안의 **가상 보관소**가 셀 배치·크레인 동작을 처리 |
| 로봇 | 서버가 **배달 묶음**을 만들어 FMS(로봇 시뮬레이터)에 전달. 경로·엘리베이터·혼잡 제어는 FMS 담당 |
| 검증 | 서버 단위 테스트 **33개**, 세대 웹 테스트 **9개** 통과(2026-10-31 재실행), 웹 타입 검사·빌드 통과, 브라우저 통합 확인 |
| 남은 일 | 실제 로봇 시뮬레이터(FMS) 메시지 규격 연동, 입력구 센서, 운영 보안 |

```
[입력 키오스크 웹] ─┐
[출력 키오스크 웹] ─┴─ ws:9001 ─▶ [Mosquitto 브로커] ◀─ tcp:1883 ─ [로봇 시뮬레이터 / FMS]
                                    ▲          ▲                         │ 로봇 상태
                              tcp:1883      tcp:1883 ◀───────────────────┘
  [보관소 서버: SQLite · 가상 보관소 · 묶음 구성 · 인증]   [세대 웹 서버(Node, :4180)] ◀─ HTTP ─ 입주민 휴대폰
```

---

## 2. 진행 경과

### 2-1. 1차 구현: Python Tkinter 키오스크 (`kiosk/`, 현재 사용 안 함)

- 요청: 보관소 입력(택배기사)·출력(사람/로봇) 키오스크, MQTT 기반, VSCode 실행 가이드
- 만든 것: Tkinter 입력·출력 키오스크, paho-mqtt 래퍼, 단순화한 모의 서버, 프로토콜 문서, README
- 해결한 문제
  - `ModuleNotFoundError: paho` → 가상환경(.venv)을 쓰지 않고 실행한 것이 원인
  - `ConnectionRefusedError` → MQTT 브로커가 없던 것이 원인. `mock_server.py`는 브로커가 아니라 브로커에 접속하는 클라이언트임
  - paho 2.x 경고 → 콜백 API v2로 변경, 서버는 `connect_async`(자동 재연결)로 변경

### 2-2. 웹 디자인 시안 → 명세 작성 (v1 ~ v3.3)

사용자가 보낸 웹 시안(LastGate 스마트 택배 키오스크, 3단계 접수 화면)을 기준으로, 코드를 바꾸기 전에 명세를 여러 차례 다듬었습니다.

| 버전 | 주요 결정 |
|---|---|
| v1 | 웹 전환 명세 초안 (브라우저↔MQTT 방식, 신규 필드, 프로토콜 확장) |
| v2 | 접수번호 `YYYYMMDD-XXXXXXXX`(LG 접두사 없음) · ZONE 제외 · **방안 A(WebSocket + mqtt.js)** · 인증코드는 항상 발급하되 기사 화면에는 표시 안 함 · 입력·출력 모두 웹 · 입력은 접수만, 마지막 화면은 최소 정보 |
| v3 | 기본 수령 방식 **로봇 배달** · 세대 토글(미적재 물품 일괄 변경) + 물품별 변경(토글이 직접 수령이면 로봇 선택 불가) · 보관소에 로봇 배달 물품이 1개라도 있으면 Job 발행 · 출력 키오스크는 ID/PW 로그인 + 표 · 101~106동 × 101~412호 |
| v3.1 | **보관소 시뮬레이터 불필요**(키오스크 [투입 완료] 이벤트 + 가상 보관소) · 혼잡 제어는 FMS · 초기 비밀번호 `1234` · 동당 1라인 · 로봇이 실어 가기 전이면 키오스크 수령 가능 · **늦은 확정**(로봇 도착 시 묶음 재계산) |
| v3.2 | 엘리베이터 정보 제외(FMS가 결정) → 묶음 기준은 `동` · 공용 박스를 소형 칸 단위로 모델링(S1·M4·L8, 2층 × 8칸) · 묶음 알고리즘과 FMS 전달 형식 정의 |
| v3.3 | 한 층 = **1×8** · 층별 하역 순서 무관 · 묶음당 **최대 6개 동** · 150kg은 정의 값 · "많은 양" = **부피(박스 채움)** 기준 |

### 2-3. 2차 구현: 웹 키오스크 + 보관소 서버

- `server/`, `web/`, `broker/`, `.vscode/`, `README.md`, `protocol.md` 작성
- 테스트용 브로커(11883/19001)를 따로 띄워 사용자 브로커·DB와 겹치지 않게 통합 검증
- 검증 중 고친 것: 입력 직후 바로 Enter를 누르면 다음 단계로 넘어가지 않던 문제(바코드 스캐너 대비, 입력창의 실제 값으로 판단), 로그에 `Mode.DIRECT`로 찍히던 문제(Enum `__str__` 추가)

### 2-4. 구현 이후 질문·수정

| 주제 | 내용 |
|---|---|
| macOS 빌드가 멈춤 | iCloud로 동기화되는 Desktop 폴더라 `node_modules` 첫 읽기가 파일당 16~23초 → 프로젝트를 `~/2026_makerton`으로 이동 |
| `npm install` 경고 | 취약점은 개발 서버 전용 esbuild 문제(vite 5 범위에서는 해결 불가, `npm audit fix --force`는 Vite 8로 올라가므로 실행 금지). install-scripts 경고는 npm 정책 안내로 동작 영향 없음 |
| "오늘 등록 n건" 기준 | 브라우저 저장값 → **서버 DB 기준 하루 건수**(키오스크별, KST, 투입 완료 기준)로 변경. 자정이 지나면 자동으로 다시 조회 |
| 출력 키오스크에 택배가 안 보임 | 서버는 정상. 기본값이 로봇 배달이라 FMS 대역이 몇 초 만에 실어 가 배달 완료 처리 → `set_mode`로 직접 수령 전환, `fms_stub --arrive 60`, 또는 FMS 대역 끄기 |
| FMS 전달 정보 형태 | `BUNDLE_CONFIRMED` 형식 정리 (4-4) |
| 세션 정리 문서 | 이 문서(`SESSION_SUMMARY.md`) 작성 → 이번에 전체 갱신 |
| 큐브형(AutoStore) 보관소 검토 | 적용 가능성, 세대 수별 크기, 다른 건물 유형 조건, 보관함 공유 문제, 보관함 커스텀 (10장) |

### 2-5. 3차 구현: 세대 웹(`end_user_wep`) 연동

- 다른 작업자가 만든 세대 웹(자체 SQLite + REST API + 화면)을 **화면 틀·디자인·REST API 형태를 유지**한 채 우리 명세와 호환되게 조정
- 확정한 방식(추천안)
  - **A. Node 서버는 MQTT 중계 서버(BFF)로 유지**: 브라우저 REST → Node → MQTT → 보관소 서버. 자체 DB는 쓰지 않음
  - 회원가입 제거(계정은 보관소 서버가 288세대 미리 발급), 택배 등록 API·관리자 화면 비활성화
  - 직접 수령 인증코드 보기는 유지하되 "보조 수단"으로 문구 변경
- 보관소 서버에 세대 웹용 요청 3개(목록·인증코드·숨김)와 7일 세션, FMS 대역에 로봇 상태 발행을 추가
- 검증 중 고친 것: 세대 웹 테스트끼리 세대 기본값이 이어져 실패하던 문제(테스트마다 초기화)

---

## 3. 시스템 전제

1. 택배기사는 입력 키오스크에서 보관소에 배달할 물품을 모두 등록합니다. 입력구는 소·중·대 3개입니다.
2. 보관소는 동·호수·크기에 맞춰 물품을 배치합니다(가상 보관소).
3. 입력·출력 키오스크, 세대 웹, 보관소, 로봇은 **서버를 거쳐** 정보를 공유하고 상태가 바뀔 때마다 동기화됩니다.
4. 세대 기본 수령 방식은 **로봇 배달**이며, 세대 웹 토글로 직접 수령으로 바꿀 수 있습니다.
5. 보관소에 로봇 배달 대상 물품이 1개라도 있으면 FMS에 배달 Job을 보냅니다.
6. 출력 키오스크에서 아이디/비밀번호로 로그인해, 로봇이 아직 실어 가지 않은 택배를 직접 꺼낼 수 있습니다.

---

## 4. 확정 명세

### 4-1. 수령 방식 규칙

| 세대 토글 | 새 물품 | 물품별 변경 | 로봇 Job |
|---|---|---|---|
| ROBOT (기본) | ROBOT | 실리기 전이면 ROBOT ↔ DIRECT 변경 가능 | ROBOT 물품만 발행 |
| DIRECT | DIRECT | 로봇 배달 선택 불가 (`DENIED`) | 발행하지 않음 |

- 토글을 바꾸면 아직 실리지 않은 물품(`REGISTERED`, `STORED`, `JOB_ASSIGNED`)이 모두 새 기본값으로 바뀌고, 바뀐 건수(`changed`)를 돌려줍니다.
- 이미 발행된 Job의 물품이 모두 직접 수령으로 바뀌면 로봇 도착 시 `JOB_CANCELLED`(`NO_ITEMS`)로 취소됩니다.
- 배달에 2회 실패하면 그 물품은 직접 수령으로 자동 전환됩니다.

### 4-2. 물품 상태

```
REGISTERED ─[투입 완료]→ STORED ─┬─ 출력 키오스크 수령 → PICKED
   └─(60초 초과)→ CANCELLED      └─ ROBOT 모드 · Job 후보 → JOB_ASSIGNED ─(로봇 도착·적재 확정)→ LOADED
                                                                     → DELIVERED / 실패 시 STORED
```

| 상태 묶음 | 상태 | 의미 |
|---|---|---|
| 수령 가능 (`PICKABLE_STATUSES`) | `STORED`, `JOB_ASSIGNED` | 출력 키오스크 수령, 수령 방식 변경 가능 |
| 완료 (`COMPLETED_STATUSES`) | `DELIVERED`, `PICKED` | 세대 웹에서 14일간 표시, 숨김 가능 |

### 4-3. 공용 박스와 가중치

| 크기 | 가중치 | 차지하는 칸 | 최대 적재 |
|---|---|---|---|
| S 소형 | 5 kg | 1칸 | 16개 |
| M 중형 | 10 kg | 4칸 (`[1–4]` 또는 `[5–8]`) | 4개 |
| L 대형 | 20 kg | 8칸 (한 층 전체) | 2개 |

- 박스: 2층 × 1×8칸 = 16칸. 조건은 **칸 합계 ≤ 16**, **무게 ≤ 150kg**
- 크기 비율 1:4:8이 나누어떨어져서 칸 합계가 16 이하이면 두 층에 항상 담깁니다.
- 꽉 채워도 최대 80kg이라 150kg 조건은 실제로 걸리지 않습니다(정의 값).

### 4-4. 배달 묶음 구성 (보관소 → FMS)

**목표 순서**: ① 박스를 가득 채운다(부피) → ② 들르는 동·세대 수 최소 → ③ 오래 기다린 물품 우선(3시간 이상)

1. 로봇 배달 대상(`STORED` + ROBOT)이 없으면 Job을 보내지 않습니다.
2. 기준 동: 3시간 넘게 기다린 물품이 있으면 그 동, 없으면 대기 칸 합계가 가장 큰 동
3. 같은 세대 → 같은 층 → 같은 동 순으로 담습니다(같은 단계면 L → M → S).
4. 칸이 남으면 동을 추가합니다(최대 6개 동). 남은 칸에 대기 물품이 **전부 들어가는 동**을 먼저 골라 그 동을 한 번에 비웁니다.
5. L → M(절반 위치) → S 순으로 층·칸을 배정합니다.
6. 로봇이 도착하면(`ROBOT_ARRIVED`) 같은 절차로 다시 계산해 최종 확정합니다(늦은 확정).

**효율 근거**: 전체 왕복 횟수는 총 부피 ÷ 16으로 정해지므로, 개수를 늘리려고 동을 섞어도 왕복은 줄지 않고 이동만 늘어납니다. 동마다 물량이 적을 때는 여러 동 묶음이 왕복을 크게 줄입니다(예: 3회 → 1회).

**흐름**: `DELIVERY_JOB`(예상 묶음) → `ROBOT_ARRIVED` → `BUNDLE_CONFIRMED` 또는 `JOB_CANCELLED` → `DELIVERY_RESULT`(물품별) → `JOB_DONE`

```jsonc
// 서버 → locker/robot/bundle
{ "type": "BUNDLE_CONFIRMED", "job_id": "J20261031-0002", "robot_id": "R1",
  "items": [
    { "receipt_no": "20261031-BF640BB8", "dong": 106, "ho": 206, "size": "M", "layer": 1, "cells": [1, 2, 3, 4] },
    { "receipt_no": "20261031-3A4B5C6D", "dong": 104, "ho": 204, "size": "S", "layer": 2, "cells": [1] }
  ],
  "summary": { "count": { "S": 1, "M": 1, "L": 0 }, "units": { "layer1": 4, "layer2": 1, "total": 5 },
               "weight_kg": 15, "dongs": [104, 106], "households": 2 },
  "timestamp": "2026-10-31T18:49:15+09:00" }
```

- 필수 정보는 동·호수·크기. `receipt_no`는 배달 결과 보고 때 물품을 구분하는 키
- 경로·엘리베이터·개인정보·인증코드는 보내지 않음

### 4-5. 단지·계정·세션

- 101~106동 × 101~412호(층 1~4, 호 01~12) = **288세대**. 서버 첫 실행 때 자동 생성
- 아이디 `동-호`(예: `101-412`), 초기 비밀번호 `1234` (bcrypt 해시 저장)
- 출력 키오스크와 세대 웹은 **같은 계정**을 씀

| 로그인 경로 | 세션 유지 | 비고 |
|---|---|---|
| 출력 키오스크 | 10분 (조작 시 연장) + 화면 60초 무조작 시 자동 로그아웃 | 공용 단말 |
| 세대 웹 (`channel: "RESIDENT"`) | 7일 | 개인 기기. 세대 웹 서버는 쿠키 `lg_session`(7일)으로 따로 관리 |

### 4-6. 세대 웹 동작

| 기능 | 동작 |
|---|---|
| 내 택배 | 진행 중 택배 전부 + 최근 14일 안에 배송·수령이 끝난 택배(숨긴 것 제외) |
| 기본 설정(토글) | 바꾸는 즉시 미적재 택배 일괄 변경, 바뀐 건수를 안내 |
| 택배별 변경 | 여러 개 선택 → [로봇 배송] / [직접 수령]. 토글이 직접 수령이면 [로봇 배송] 비활성 |
| 인증코드 | 내 택배 · 보관 중 · 직접 수령일 때만. 60초 뒤 숨김. 수령은 출력 키오스크 로그인이 기본, 코드는 보조 수단 |
| 완료 택배 삭제 | `DELIVERED`·`PICKED`만 목록에서 숨김 |
| 로봇 현황 | FMS의 `locker/robot/{id}/state`(retained, 10초 주기)를 구독. 30초 넘게 소식이 없으면 "통신 끊김" |

| 보관소 상태 | 세대 웹 표시 | 수령 방법 변경 |
|---|---|---|
| `STORED`, `JOB_ASSIGNED` | 보관 완료 / 로봇 운송 준비 중 | 가능 |
| `LOADED` | 로봇 배송 중 (`IN_TRANSIT`) | 불가 |
| `DELIVERED` | 배송 완료 | 불가, 삭제 가능 |
| `PICKED` | 수령 완료 (`PICKED_UP`) | 불가, 삭제 가능 |
| `REGISTERED`, `CANCELLED` | 표시 안 함 | — |

---

## 5. 화면

### 입력 키오스크 (`/input`, 택배기사)

| 단계 | 내용 |
|---|---|
| 상단 | 진행 스텝바, **오늘 등록 n건**(서버 기준, 키오스크별), [업무 종료] |
| Step 01 배송 주소 | 101~106동 카드 + 호수 입력(범위 검증). 다음 물품은 직전 동이 미리 선택됨 |
| Step 02 택배 정보 | 크기 S/M/L + 송장번호(선택, 바코드 스캐너 입력 가능) |
| Step 03 접수 확인 | 동·호수, 크기, 송장번호 확인 → [택배 접수] |
| Step 04 투입 안내 | **"M 입력구에 넣어주세요"** + 남은 시간 → [투입 완료] → "등록 완료 + 접수번호" → 3초 뒤 다음 물품 |

- 인증코드는 기사 화면에 표시하지 않음. [업무 종료]는 오늘 건수를 보여주고 입력 화면만 처음 상태로 돌림
- 키오스크 번호는 `/input?id=INPUT-02`로 구분

### 출력 키오스크 (`/output`, 세대인)

- 홈 = 아이디/비밀번호 로그인(화면 키패드)
- 로그인 후 표: **접수번호 | 도착일 | 수령([택배 수령])**. 누르면 수령 출력구로 나오고 행 삭제
- 로봇이 실어 가면 서버 알림(`PARCELS_UPDATE`)으로 행이 자동으로 사라짐

### 시작 화면 (`/`)

키오스크 선택 + 보관소 상태(크기별 셀 사용량, 로봇·직접 수령 대기 건수, 진행 중 Job)

### 세대 웹 (`http://localhost:4180`, 입주민 휴대폰)

- 기존 디자인(CSS) 유지. 로그인(아이디 `101-412` + 비밀번호), 요약 카드(보관 중 · 로봇 배송 중 · 직접 수령 대기 등), 기본 설정 패널, 택배 목록(선택·일괄 변경·인증코드·삭제), 로봇 현황, 상단 연결 표시(보관소 연결 끊김 시 오프라인)

---

## 6. 결과물 파일 명세

줄 수는 2026-10-31 기준입니다. ★는 이번 세션에서 새로 만들거나 크게 고친 파일입니다.

### 6-1. 루트

| 파일 | 줄 | 내용 |
|---|---|---|
| `README.md` ★ | 188 | 준비물, 설치(macOS·Windows), 실행(VSCode 작업 / 터미널 5개), 접속 주소, 시연 순서, 테스트 도구, FMS 연동, 주요 설정, 다른 PC 접속, 문제 해결 |
| `protocol.md` ★ | 209 | MQTT 프로토콜 v3.3: 토픽 표, 입력·출력 키오스크, 수령 방식, 4-1 세대 웹, 5 서버↔FMS, 상태 요약, 물품 상태 |
| `SESSION_SUMMARY.md` ★ | — | 이 문서 |
| `.gitignore` ★ | 11 | venv, DB(`server/data/`, `end_user_wep/data/`), `node_modules`, `dist`, 캐시 |
| `.vscode/tasks.json` ★ | 84 | 작업: 브로커 · 서버 · FMS 대역 · 웹 · 세대 웹 · **전체 실행**(5개 병렬) · 테스트 택배 12건 · 서버 단위 테스트 · 세대 웹 테스트 (macOS·Windows 명령 분리) |
| `.vscode/settings.json` | 4 | VSCode 작업 공간 설정 |
| `broker/mosquitto.conf` ★ | 14 | `listener 1883`(mqtt) + `listener 9001`(websockets), 익명 허용(시연용), persistence 끔 |

### 6-2. 보관소 서버 `server/` (Python 3.10+, `paho-mqtt==2.1.0`, `bcrypt==4.2.1`)

| 파일 | 줄 | 내용 |
|---|---|---|
| `server.py` | 49 | 실행 진입점. MQTT 연결 → `LockerCore` 부팅 → 하트비트 루프. `--reset`으로 DB 초기화 |
| `config.py` | 133 | 브로커·DB 경로(환경변수), 토픽 상수, 단지 규모, 크기별 가중치·칸 수, 박스 규격, 묶음 파라미터, 가상 랙 규격·크레인 속도, 타임아웃·세션 시간, `now_kst()`, `parse_unit()`, `all_units()` |
| `models.py` | 100 | `Status`·`Mode` Enum, `Item`(접수번호·동·호·크기·모드·상태·인증코드·송장·입력 키오스크·숨김 시각·슬롯·Job·실패 횟수 등), `Slot`, `Bundle`, 상태 묶음 상수 |
| `core.py` | 580 | `LockerCore`: 토픽별 요청 처리(접수·투입·오늘 건수·로그인·목록·수령·토글·물품별 변경·세대 목록·인증코드·숨김), Job 발행·늦은 확정·배달 결과 처리, 투입 시간 초과, 중복 요청 캐시, **커밋 후 발행(outbox)**, 상태 요약 |
| `store.py` | 244 | SQLite 스키마와 이전 DB 자동 보정(`input_kiosk`, `hidden_at` 열 추가), 세대·계정·물품·Job·이벤트 로그 CRUD, `resident_items()`, `count_stored_on()` |
| `auth.py` | 69 | bcrypt 해시·검증, `SessionManager`(세션별 유지 시간 `ttl_sec`, 조회 시 연장, 세대별 세션 조회, 만료 정리) |
| `bundler.py` | 203 | `build_bundle()`(4-4 알고리즘), `assign_cells()`(L→M→S 층·칸 배정), `bundle_metrics()` |
| `storage.py` | 162 | `StorageAdapter` 인터페이스 + `VirtualStorage`: 랙 A/B × 24열 × 6단, 체류시간 띠(B1/B2/B3), 체비쇼프 크레인 시간, 같은 동 클러스터 비용으로 셀 선택 |
| `fms_adapter.py` | 90 | FMS 메시지 생성·해석. **실제 로봇 시뮬레이터 연동 시 이 파일만 수정** |
| `mqtt_client.py` | 99 | paho 2.x 래퍼: 토픽별 핸들러, 자동 재연결, LWT(`online`/`offline`), JSON 발행 |
| `requirements.txt` | 2 | 의존성 |
| `tools/rpc.py` | 45 | 도구용 요청·응답 헬퍼 |
| `tools/seed_packages.py` | 48 | 무작위 동·호수·크기로 접수 + 투입 완료 N건 |
| `tools/set_mode.py` | 57 | 명령줄 수령 방식 변경(세대 토글 · 물품별) 및 목록 보기 |
| `tools/fms_stub.py` ★ | 115 | FMS 대역: Job 수신 → N초 뒤 도착 → 물품별 배달 결과(실패 확률 조절) → 완료. **로봇 상태 retained 발행**(보관소로 이동 중 → 적재 중 → 배송 중 → 대기 중, 배터리, 10초 하트비트, 종료 시 통신 끊김) |
| `tests/test_bundler.py` | 112 | 묶음 구성 테스트(무작위 300개 묶음의 칸·무게·동 수 제약 검증 포함) |
| `tests/test_core.py` ★ | 317 | 접수 검증, 중복 요청, 투입 시간 초과, 로봇 배달 전체 흐름, 늦은 확정, 실패 2회 전환, 키오스크 수령, 수령 방식 규칙, 세션 만료, 오늘 건수·자정, 이전 DB 호환, **세대 세션 7일 · 이력·숨김 · 14일 경과 제외 · 인증코드 조건** |
| `data/locker.db` | — | 실행 시 생성되는 SQLite DB (git 제외) |

### 6-3. 웹 키오스크 `web/` (Vite 5.4.11 + React 18.3.1 + TypeScript 5.6.3, `mqtt` 5.10.1)

| 파일 | 줄 | 내용 |
|---|---|---|
| `package.json` | 24 | 스크립트 `dev` · `build`(tsc + vite) · `preview` · `typecheck`, 버전 고정 |
| `vite.config.ts` · `tsconfig.json` · `index.html` | 9 · 17 · 12 | 개발 서버 4173, TS 설정, 진입 HTML |
| `src/main.tsx` | 16 | 경로별 앱 선택(`/`, `/input`, `/output`) |
| `src/apps/Launcher.tsx` | 77 | 시작 화면: 키오스크 선택 + 보관소 상태 요약 |
| `src/apps/input/InputApp.tsx` | 365 | 입력 키오스크 4단계 흐름, 투입 대기 타이머, 오늘 등록 건수, 업무 종료 |
| `src/apps/output/OutputApp.tsx` | 245 | 출력 키오스크 로그인 키패드, 택배 표, 수령, 실시간 갱신, 무조작 로그아웃 |
| `src/shared/config.ts` | 52 | 브로커 주소(접속 호스트:9001 자동, `VITE_BROKER_URL`로 변경), 토픽, 단지 규모, 크기 정의, 호수 검증, 키오스크 번호 |
| `src/shared/mqtt.ts` | 110 | `LockerClient`: WebSocket MQTT 연결, `request_id` 요청·응답 매칭, 알림 구독 |
| `src/shared/hooks.ts` | 66 | `useLocker`, `useNow`, `useTodayCount`, `msUntilKstMidnight` |
| `src/shared/ui.tsx` · `icons.tsx` · `styles.css` | 125 · 82 · 260 | 공통 UI 컴포넌트(스텝바·카드·버튼·연결 배지·토스트), 아이콘, 시안 기반 스타일 |
| `dist/` | — | 빌드 결과물 (git 제외) |

### 6-4. 세대 웹 `end_user_wep/` (Node 20.6+, 프레임워크 없이 `node:http`, `mqtt` 5.10.1)

**사용 중인 파일**

| 파일 | 줄 | 내용 |
|---|---|---|
| `package.json` ★ | 15 | v1.1.0, 스크립트 `start` · `start:env`(.env 사용) · `test` |
| `.env.example` ★ | 8 | `PORT=4180`, `HOST`, `LOCKER_BROKER_HOST/PORT`, `LOCKER_BROKER_URL` |
| `server.mjs` ★ | 46 | 서버 시작. 브로커 주소 결정, 연결 상태 로그, 종료 처리 |
| `src/locker-client.mjs` ★ 신규 | 81 | 보관소 서버 MQTT 클라이언트: `RESIDENT-WEB-xxxxxx` 접속, 전용 응답 토픽 구독, 5초 타임아웃 요청, 로봇 상태(`locker/robot/+/state`) 구독·보관, `LockerUnavailableError` |
| `src/user-service.mjs` ★ | 169 | 로그인(`channel: RESIDENT`)·세션 저장소(메모리, sha256 토큰), 기본 설정·택배별 변경·목록·인증코드·숨김·로봇 현황. 보관소 응답 코드 → HTTP 오류 변환. **기존 함수 이름·반환 형태 유지** |
| `src/parcel-service.mjs` ★ | 55 | 동·크기·상태 상수, 보관소 상태 → 화면 상태 변환, `DIRECT` ↔ `PICKUP` 변환 |
| `src/api-server.mjs` ★ | 140 | REST API와 정적 파일(user.html/js/css만). 회원가입 410, 관리자·택배 등록·추적 API 제거 |
| `public/user.html` ★ | 116 | 로그인(아이디), 기본 설정, 택배 목록, 로봇 현황. 회원가입 탭 제거, 문구 수정 |
| `public/assets/user.js` ★ | 396 | 화면 로직: 연결 상태 표시, 토글 후 새로고침·변경 건수 안내, 로봇 버튼 비활성, 수령 완료 상태, 인증코드 문구 |
| `public/assets/user.css` ★ | 23 | 기존 스타일 + `PICKED_UP` 상태, 오프라인 표시 |
| `tests/api.test.mjs` ★ | 225 | 가짜 보관소 클라이언트로 9개 테스트: 비활성 경로, 로그인, 상태 변환, 토글 일괄 변경, 물품별 제한, 인증코드, 숨김, 로봇 통신 끊김, 503/401 |
| `README.md` ★ | 150 | 구조, 실행, 환경변수, 동작·상태 표, REST API, 오류 코드, FMS 로봇 상태 규격, 테스트 |

**남겨 둔 예전 파일 (사용 안 함)**

| 파일 | 비고 |
|---|---|
| `src/db.mjs`, `data/lastgate.sqlite*` | 예전 자체 SQLite. 더 이상 읽지 않음 |
| `public/index.html`, `assets/kiosk.js`, `assets/styles.css` | 예전 기사 키오스크 → `web/`의 입력 키오스크로 대체 |
| `public/admin.html`, `assets/admin.js` | 예전 운영자 데모 |
| `lastgate_v2_update.mjs` | 예전 소스로 파일을 **덮어쓰는** 도구. 실행 금지 |

### 6-5. 1차 버전 `kiosk/` (사용 안 함)

Tkinter 입력·출력 키오스크(`storage_input_app.py`, `storage_output_app.py`), `mock_server.py`, `protocol.md` 등. 필요 없으면 삭제해도 됩니다.

---

## 7. 인터페이스

### 7-1. MQTT 토픽 (모두 JSON, QoS 1)

| 토픽 | 방향 | 메시지 |
|---|---|---|
| `locker/input/register` · `port_confirm` · `stats` | 입력 키오스크 → 서버 | 접수 · 투입 완료 · 오늘 등록 건수 |
| `locker/auth/login` · `logout` | 출력 키오스크·세대 웹 → 서버 | 로그인(세대 웹은 `channel: "RESIDENT"`) · 로그아웃 |
| `locker/output/parcels` · `retrieve` | 출력 키오스크 → 서버 | 목록 · 택배 수령 |
| `locker/resident/default_mode` · `item_mode` | 세대 웹 · `set_mode` → 서버 | 토글 · 물품별 변경 |
| `locker/resident/parcels` · `pickup_code` · `hide` | 세대 웹 → 서버 | 이력 포함 목록 · 인증코드 · 완료 택배 숨김 |
| `locker/client/{client_id}/res` | 서버 → 요청자 | 모든 응답, `PARCELS_UPDATE`, `REGISTER_CANCELLED` |
| `locker/state/summary` (retained) | 서버 → 전체 | 상태 요약(변경 시 + 10초 하트비트) |
| `locker/storage/log` | 서버 → 전체 | 가상 보관소 크레인 동작 로그 |
| `locker/robot/job` · `bundle` | 서버 → FMS | 예상 묶음 · 최종 묶음/취소 |
| `locker/robot/event` | FMS → 서버 | 도착 · 배달 결과 · 완료 |
| `locker/robot/{robot_id}/state` (retained) | FMS → 세대 웹 | 로봇 상태·위치·배터리 (서버는 사용 안 함) |
| `locker/client/{id}/online`, `locker/server/online` (retained) | 각 클라이언트(LWT) | 접속 상태 |

공통 규칙: 요청에 `request_id`·`client_id`를 넣고, 서버는 요청자 전용 토픽으로만 응답하며, `(client_id, request_id)`로 중복 요청을 한 번만 처리합니다. 메시지 예시는 [protocol.md](protocol.md)를 보세요.

### 7-2. 세대 웹 REST API (`:4180`)

| Method | 경로 | 내용 |
|---|---|---|
| `GET` | `/api/health` | `{ ok, locker: "connected" \| "disconnected" }` |
| `GET` | `/api/config` | 동·크기·상태 목록 |
| `POST` | `/api/auth/login` · `/api/auth/logout` | `{ userId, password }` → 쿠키 `lg_session` |
| `POST` | `/api/auth/register` | 410 `REGISTRATION_DISABLED` |
| `GET` | `/api/me` | 로그인한 세대 정보 |
| `GET` / `PATCH` | `/api/user/preferences` | 기본 수령 방법 조회/변경 → `changed` |
| `GET` | `/api/user/parcels` | 내 택배 목록 |
| `PATCH` | `/api/user/parcels/:id/delivery` | 택배별 변경 `{ method: "PICKUP" \| "ROBOT" }` |
| `GET` | `/api/user/parcels/:id/pickup-code` | 인증코드 |
| `DELETE` | `/api/user/parcels/:id` | 완료 택배 숨김 |
| `GET` | `/api/user/robots` | 로봇 현황 |

| 보관소 응답 | HTTP |
|---|---|
| `DENIED`, `NOT_CHANGEABLE` | 409 `DELIVERY_CHOICE_LOCKED` |
| `NOT_AVAILABLE` / `NOT_COMPLETED` | 409 `PICKUP_CODE_UNAVAILABLE` / `PARCEL_NOT_DELIVERED` |
| `NOT_FOUND` / `INVALID` | 404 / 400 |
| `EXPIRED_SESSION` | 401 `AUTH_REQUIRED` |
| 브로커·서버 끊김, 5초 무응답 | 503 `LOCKER_UNAVAILABLE` |

---

## 8. 주요 설정값 (`server/config.py`)

| 설정 | 값 | 의미 |
|---|---|---|
| `VALID_DONGS`, `FLOORS`, `UNITS_PER_FLOOR` | 101~106, 4, 12 | 단지 규모 (웹은 `web/src/shared/config.ts`도 함께 수정) |
| `SEED_PASSWORD`, `BCRYPT_ROUNDS` | `1234`, 8 | 초기 비밀번호, 288개 계정을 빠르게 만들기 위한 해시 강도 |
| `SIZE_WEIGHT`, `SIZE_UNITS` | S5/M10/L20kg, S1/M4/L8칸 | 배달 가중치, 박스 칸 수 |
| `BOX_LAYERS`, `LAYER_UNITS`, `ROBOT_MAX_WEIGHT` | 2, 8, 150 | 공용 박스 규격 |
| `MAX_DONGS_PER_BUNDLE`, `AGING_LIMIT_SEC` | 6, 3시간 | 묶음 최대 동 수, 우선 배달 대기시간 |
| `MAX_ACTIVE_JOBS` | 1 | 동시 진행 Job 수 (= 로봇 대수) |
| `DEFAULT_MODE`, `MAX_FAIL` | ROBOT, 2 | 세대 기본 수령 방식, 직접 수령 전환 실패 횟수 |
| `PORT_TIMEOUT_SEC` | 60 | 접수 후 투입 대기 |
| `SESSION_TTL_SEC`, `RESIDENT_SESSION_TTL_SEC` | 600, 7일 | 키오스크·세대 웹 세션 |
| `RESIDENT_HISTORY_DAYS`, `HEARTBEAT_SEC` | 14, 10 | 세대 웹 완료 택배 표시 기간, 상태 요약 주기 |
| `RACK_*`, `BAND_COLUMNS`, `CRANE_*`, `PLACE_*` | A/B × 24열 × 6단 등 | 가상 보관소 규격과 셀 선택 가중치 |

---

## 9. 실행 요약과 검증 기록

### 실행 (자세한 내용은 README)

1. 설치: `server`에 venv + `pip install -r requirements.txt`, `web`과 `end_user_wep`에 각각 `npm install`
2. Homebrew Mosquitto 서비스가 떠 있으면 `brew services stop mosquitto` (9001 WebSocket이 없음)
3. VSCode 명령 팔레트 → **Tasks: Run Task → LastGate: 전체 실행** (브로커·서버·FMS 대역·웹·세대 웹)
4. 접속: `http://localhost:4173`(시작) · `/input` · `/output` · `http://localhost:4180`(세대 웹)
5. 로그인: `101-412` / `1234`. 직접 수령 흐름은 세대 웹 토글이나 `python -m tools.set_mode 101-412 DIRECT`로 전환

### 검증

- **서버 단위 테스트 33개 통과**: 4-1~4-6 규칙 전반(6-2의 `tests/` 참고)
- **세대 웹 테스트 9개 통과**
- **브라우저 통합**(테스트 브로커 11883/19001, 임시 DB)
  - 입력: 접수 → 투입 안내 → 등록 완료, 범위 밖 호수 거부, 오늘 건수가 새로고침·업무 종료 후에도 유지되고 키오스크별로 분리
  - 로봇: Job 발행 → 도착 → 묶음 확정 → 배달 완료, 출력 키오스크 행 자동 삭제. 25건 투입 시 1건으로 발행된 Job이 도착 시점에 16/16칸·10건·3개 동 묶음으로 확정
  - 출력: 직접 수령 세대 택배 실시간 표시, [택배 수령] 동작
  - 세대 웹: 로그인 → 목록 → 배송 완료 반영 → 삭제, 로봇 R1 상태 표시, 토글 변경 시 2건 일괄 변경 + 기존 Job은 도착 시 `NO_ITEMS` 취소, [로봇 배송] 비활성, 인증코드가 DB 값과 일치

---

## 10. 설계 검토: 큐브형(AutoStore형) 보관소

질의응답으로 검토한 내용입니다(코드에는 반영하지 않음). 통계 수치 일부는 가정값입니다.

| 주제 | 결론 |
|---|---|
| 적용 가능성 | 가능. 체류시간 띠(위쪽 층 = 출력구에 가까움), 같은 동 모으기, `StorageAdapter` 구조가 그대로 맞음. 보관 단위가 셀 → **보관함(bin)**, 꺼내는 비용이 "위에 쌓인 보관함 수"로 바뀜 |
| 제약 | 표준 보관함 안쪽 603×403mm·높이 220/330/425mm·30kg이라 대형 상당수는 별도 구역 필요. 보관함 → 로봇 박스로 옮기는 장치 필요(박스 한 층을 보관함 2개 크기로 잡으면 S1·M4·L8 비율 유지). 층고 5m 이상 필요 → 지하주차장(2.3~2.7m) 대신 단지 입구 1층 전용동 권장 |
| 세대 수별 크기 | 세대당 하루 약 0.75개, 설계일 1.8배, 평균 체류 0.32일, 99% 여유로 **세대당 약 0.8칸**. 300세대 약 255칸 · 1,000세대 약 800칸 · 3,000세대 약 2,310칸. 로봇이 늦어져 체류가 늘면 칸 수가 비례해 늘어남(로봇 대수와 보관소 크기는 맞바꾸는 관계). 1,000세대 약 75㎡, 로봇 약 9대(개략) |
| 다른 건물 유형 | 주소가 (건물, 층, 호)로 표현되면 서버는 `config.parse_unit()`만 바꾸면 됨. 건물 쪽 조건: 충분한 물동량, 입구 근처 보관 공간(층고·하중), 턱 없는 경로, 자동문·엘리베이터 연동, 실외 구간 제도 |
| 보관함 공유 문제 | 포트는 보관함을 **열린 채 통째로** 내주므로, 여러 세대 택배를 한 보관함에 넣으면 직접 수령 주민에게 다른 세대 택배가 보이고 손이 닿음. 직접 수령 물품만 세대별 보관함에 분리(④) + 세대 전용 보관함(①) 조합 권장. 현재 가상 보관소는 셀당 1개라 해당 없음 |
| 보관함 커스텀 | 바닥 크기는 고정, 높이 3종 선택·FlexBins로 혼용 가능, 칸막이로 최대 32칸(425mm는 8칸). 칸막이는 뚜껑이 아니므로 공유 문제는 해결 안 됨. 자체 설계라면 크기 자유(그리드·집게·포트가 함께 바뀜) |

---

## 11. 남은 작업과 참고 사항

| 항목 | 상태 |
|---|---|
| 실제 로봇 시뮬레이터(FMS) 연동 | 그쪽 토픽·메시지 예시가 필요. 받으면 `fms_adapter.py`만 맞추면 됨. 로봇 상태는 `locker/robot/{id}/state` 형식으로 보내 달라고 전달 필요(`end_user_wep/README.md` 5장). 그 전까지는 `fms_stub` 사용 |
| 입력구 센서 | 미구현. [투입 완료] 버튼으로 대체. 센서는 같은 `PORT_DETECTED`를 `source: "SENSOR"`로 보내면 됨 |
| 실행 중인 서버 | 서버 코드가 바뀌었으므로 **실행 중인 `server.py`는 재시작 필요**. 기존 DB는 시작 시 자동 보정 |
| 보안 | 시연용 내부망 설정(익명 접속, HTTP). 운영 시 브로커 계정·ACL, TLS/`wss`, HTTPS, 비밀번호 변경 기능, 세대 웹 세션 공유 저장소 필요 |
| npm 취약점 경고 | 개발 서버 전용 esbuild 문제. 시연 영향 없음 |
| 예전 파일 | `kiosk/`, `end_user_wep`의 예전 파일(6-4) 정리 여부 결정 필요 |
| 버전 관리 | 현재 폴더는 git 저장소가 아님. 커밋하지 않은 상태 |
