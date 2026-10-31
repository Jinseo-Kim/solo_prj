# 보관소 키오스크 (입력/출력) — MQTT 기반

아파트/오피스텔 단지용 로봇 택배 물류 시스템의 **보관소 키오스크** 프로그램입니다.
택배기사가 물품을 넣는 **입력 키오스크**와, 세대인(사람)/로봇이 물품을 꺼내는
**출력 키오스크**로 구성되며, 내부 서버의 **MQTT 브로커**를 통해 시뮬레이션과
연동됩니다.

```
[입력 키오스크]  ─┐
                 ├─(MQTT)─> [내부 서버 / 시뮬레이션]  ← mock_server.py 로 대체 가능
[출력 키오스크]  ─┘
```

---

## 1. 구성 파일

| 파일 | 설명 |
|---|---|
| `main.py` | 런처(모드 선택). 입력/출력 키오스크 실행 |
| `storage_input_app.py` | 입력 키오스크 (택배기사) |
| `storage_output_app.py` | 출력 키오스크 (사람 직접 수령 / 로봇 배차) |
| `mqtt_client.py` | MQTT 공통 래퍼 |
| `config.py` | 브로커 주소, 토픽, 단지 메타데이터 (여기만 바꾸면 됨) |
| `models.py` | 도메인 데이터 구조 (Item / Slot) |
| `ui_common.py` | 키오스크 공통 UI 위젯 |
| `mock_server.py` | **모의 보관소 서버** — 시뮬레이션 연결 전 단독 테스트용 |
| `seed_packages.py` | 테스트용 택배 자동 투입 |
| `protocol.md` | MQTT 토픽/메시지 명세 (시뮬레이션 연동 규격) |

---

## 2. 실행 환경

- **Python 3.10+** (개발·검증: 3.12)
- **Tkinter** — GUI (대부분의 Python 설치에 기본 포함. 아래 참고)
- **paho-mqtt 2.x** — MQTT 클라이언트 (`requirements.txt`)
- **MQTT 브로커** — 내부 서버. 로컬 테스트는 **Mosquitto** 권장
- **IDE: VSCode** + Python 확장

### Tkinter 확인
```bash
python3 -m tkinter
```
작은 창이 뜨면 설치되어 있습니다. 없을 경우:
- **macOS (Homebrew Python)**: `brew install python-tk`
- **Ubuntu/Debian**: `sudo apt install python3-tk`
- **Windows**: 공식 설치본에 기본 포함 (설치 시 "tcl/tk" 옵션 유지)

---

## 3. 설치 (VSCode)

VSCode에서 이 `kiosk/` 폴더를 열고, 통합 터미널(``Ctrl+` ``)에서:

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

```bash
pip install -r requirements.txt
```

VSCode 우측 하단/명령 팔레트(`Python: Select Interpreter`)에서 `.venv`를 선택하세요.

---

## 4. MQTT 브로커 준비 (로컬 테스트)

내부 서버가 아직 없으면 로컬 Mosquitto로 테스트합니다.

- **macOS**: `brew install mosquitto && brew services start mosquitto`
- **Ubuntu**: `sudo apt install mosquitto && sudo systemctl start mosquitto`
- **Docker (공통)**:
  ```bash
  docker run -it --rm -p 1883:1883 eclipse-mosquitto
  ```

> 실제 시뮬레이션/내부 서버에 붙일 때는 브로커만 그쪽을 가리키면 됩니다:
> ```bash
> export LOCKER_BROKER_HOST=192.168.0.50   # 내부 서버 IP
> export LOCKER_BROKER_PORT=1883
> ```
> (Windows PowerShell: `$env:LOCKER_BROKER_HOST="192.168.0.50"`)
> 인증이 필요하면 `LOCKER_BROKER_USER`, `LOCKER_BROKER_PASS` 도 설정.

---

## 5. 실행 순서

터미널 **3~4개**(또는 VSCode 터미널 분할)를 사용합니다.

**① 모의 서버** (실제 시뮬레이션이 있으면 생략):
```bash
python mock_server.py
```

**② 입력 키오스크** (택배기사):
```bash
python main.py input
```

**③ 출력 키오스크** (사람/로봇):
```bash
python main.py output
```

**④ (선택) 테스트 택배 자동 투입** — 로봇 배차를 바로 보고 싶을 때:
```bash
python seed_packages.py 15
```

> `python main.py` 만 실행하면 모드 선택 화면이 먼저 뜹니다.

---

## 6. 사용 흐름

**입력 (택배기사)**
1. 동 입력 → `다음` → 호수 입력 → `다음`
2. 크기(소/중/대) 선택 → `접수하기`
3. 무게 측정(데모는 모의) 후 서버가 **적재 셀 위치 / 입력구 / 수령코드(PICKUP)** 안내

**출력 — 직접 수령 (사람)**
1. `직접 수령` → 수령 코드(PIN 6자리) 입력 → `인증`
2. 매칭되면 수령 출력구로 인출

**출력 — 로봇 배차**
1. `로봇 배차` → 대상 라인 선택(또는 자동) → `배차 요청`
2. 서버가 우선순위·층 묶음으로 **적재 batch**와 **SCAN 경로** 계산 → 안내

---

## 7. 시뮬레이션 연동

키오스크는 오직 `protocol.md` 의 MQTT 메시지만 주고받습니다.
시뮬레이션 측에서 아래 토픽을 구현하면 `mock_server.py` 를 대체할 수 있습니다.

- 구독: `locker/input/request`, `locker/output/pickup/request`, `locker/output/robot/request`
- 발행: `locker/input/response`, `locker/output/pickup/response`, `locker/output/robot/response`, `locker/status`

메시지 스키마와 상태코드는 [`protocol.md`](protocol.md) 참고.
단지 규모·동/호수/라인 매핑은 [`config.py`](config.py) 에서 조정합니다.

---

## 8. 자주 겪는 문제

| 증상 | 원인 / 해결 |
|---|---|
| 하단에 "서버 연결 안 됨" 빨간 불 | 브로커 미실행 또는 주소 오류. 4장 / `LOCKER_BROKER_HOST` 확인 |
| `ModuleNotFoundError: paho` | venv 미활성화 또는 `pip install -r requirements.txt` 누락 |
| `No module named _tkinter` | 2장 Tkinter 설치 참고 |
| 로봇 배차가 "대기 물품 없음" | 먼저 입력하거나 `seed_packages.py` 실행 (DOOR 옵션 물품만 로봇 대상) |
