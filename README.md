# LastGate 보관소 시스템

아파트 단지용 로봇 택배 보관소의 **서버**, **웹 키오스크**(입력·출력), **세대 웹**입니다.
모든 구성 요소는 내부 서버의 **MQTT 브로커**를 통해 정보를 주고받습니다.

```
[입력 키오스크 웹] ─┐
[출력 키오스크 웹] ─┴─ ws:9001 ─▶ [Mosquitto 브로커] ◀─ tcp:1883 ─ [로봇 시뮬레이터 / FMS]
                                    ▲          ▲
                              tcp:1883      tcp:1883
  [보관소 서버: SQLite · 가상 보관소 · 묶음 구성 · 인증]   [세대 웹 서버(Node)] ◀─ HTTP ─ 입주민 휴대폰
```

| 폴더 | 내용 |
|---|---|
| `server/` | 보관소 서버(Python). 접수·보관·수령·로봇 배달 묶음 구성 |
| `server/tools/` | 테스트 도구: 택배 자동 접수, 수령 방식 변경(명령줄), FMS 대역 |
| `web/` | 웹 키오스크(Vite + React + TypeScript). `/input`, `/output` |
| `end_user_wep/` | 세대 웹(입주민용). 내 택배 확인, 수령 방식 토글·물품별 변경, 로봇 현황. 자세한 내용은 `end_user_wep/README.md` |
| `broker/` | Mosquitto 설정 (1883 TCP + 9001 WebSocket) |
| `protocol.md` | MQTT 토픽·메시지 규격 (로봇 시뮬레이터 연동 기준) |
| `kiosk/` | 이전 Tkinter 버전 (더 이상 사용하지 않음) |

---

## 1. 준비물

| 항목 | 버전 | macOS | Windows |
|---|---|---|---|
| Python | 3.10 이상 | `brew install python` | python.org 설치 파일 ("Add to PATH" 체크) |
| Node.js | 20 LTS 이상 | `brew install node` | nodejs.org LTS 설치 파일 |
| Mosquitto | 2.x | `brew install mosquitto` | mosquitto.org 설치 파일 (`C:\Program Files\mosquitto`) |
| VSCode | 최신 | Python 확장 설치 | Python 확장 설치 |

브로커는 Docker로 띄워도 됩니다 (프로젝트 폴더에서 실행):

```bash
docker run -it --rm -p 1883:1883 -p 9001:9001 -v "$PWD/broker/mosquitto.conf:/mosquitto/config/mosquitto.conf" eclipse-mosquitto
```

## 2. 설치 (처음 한 번)

VSCode에서 **`2026_makerton` 폴더를 열고** 통합 터미널(``Ctrl+` ``)에서 실행합니다.

**macOS**

```bash
cd server && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && cd ..
```

```bash
cd web && npm install && cd ..
```

```bash
cd end_user_wep && npm install && cd ..
```

**Windows (PowerShell)**

```bash
cd server; python -m venv .venv; .venv\Scripts\python.exe -m pip install -r requirements.txt; cd ..
```

```bash
cd web; npm install; cd ..
```

```bash
cd end_user_wep; npm install; cd ..
```

> **macOS에서 프로젝트가 Desktop/Documents 폴더에 있다면**: iCloud "데스크탑 및 문서 폴더" 동기화가 켜져 있으면
> `node_modules`의 수천 개 파일을 iCloud가 업로드하는 동안 파일 읽기가 크게 느려집니다(빌드가 수 분씩 멈춤).
> 프로젝트를 iCloud 밖(예: `~/dev`)으로 옮기거나, 아래처럼 `node_modules`를 동기화에서 빼세요.
>
> ```bash
> cd web && mv node_modules node_modules.nosync && ln -s node_modules.nosync node_modules && cd ..
> ```

## 3. 실행

### 방법 A — VSCode 작업 한 번에 실행

명령 팔레트(`Ctrl/Cmd+Shift+P`) → **Tasks: Run Task** → **LastGate: 전체 실행**
브로커, 서버, FMS 대역, 웹 키오스크, 세대 웹이 각각 전용 터미널에서 실행됩니다.

### 방법 B — 터미널 5개에서 직접 실행

macOS 기준입니다. Windows는 `.venv/bin/python`을 `.venv\Scripts\python.exe`로 바꾸면 됩니다.

```bash
mosquitto -c broker/mosquitto.conf -v
```

```bash
cd server && .venv/bin/python server.py
```

```bash
cd server && .venv/bin/python -m tools.fms_stub
```

```bash
cd web && npm run dev
```

```bash
cd end_user_wep && npm start
```

> Homebrew로 Mosquitto를 서비스로 띄워 둔 상태라면 1883 포트가 겹칩니다. 먼저 `brew services stop mosquitto`로 멈추세요.
> 기본 서비스 설정에는 WebSocket(9001)이 없어서 웹 키오스크가 연결되지 않습니다.

브라우저에서 접속:

| 주소 | 화면 |
|---|---|
| http://localhost:4173 | 시작 화면 (키오스크 선택 + 보관소 상태) |
| http://localhost:4173/input | 입력 키오스크 (택배기사) |
| http://localhost:4173/output | 출력 키오스크 (세대인) |
| http://localhost:4180 | 세대 웹 (입주민 휴대폰용) |

서버를 처음 실행하면 288세대(101~106동 × 101~412호) 계정이 자동으로 만들어집니다.
아이디는 `동-호`(예: `101-412`), 초기 비밀번호는 `1234`입니다.
DB를 처음 상태로 돌리려면 `python server.py --reset`으로 실행합니다.

## 4. 시연 순서

1. **입력**: `/input`에서 `101동` → `412` → `M` → [택배 접수] → "M 입력구에 넣어주세요" → [투입 완료] → 등록 완료
2. **로봇 배달**: 서버가 바로 Job을 발행하고, FMS 대역이 5초 뒤 "도착"을 보냅니다. 서버가 묶음을 확정하고 FMS 대역이 배달 결과를 보고합니다. (서버·FMS 터미널 로그로 확인)
3. **직접 수령**: 로봇이 가져가기 전이면 `/output`에서 `101-412` / `1234`로 로그인 → [택배 수령]
   - 수령 흐름을 천천히 보려면 FMS 대역을 `--arrive 60`으로 실행하거나, 세대를 직접 수령으로 바꿉니다.
     세대 웹(`http://localhost:4180`, `101-412` / `1234`)의 **내 택배 → 기본 설정**에서 바꾸거나,
     `.venv/bin/python -m tools.set_mode 101-412 DIRECT`를 실행합니다.
3-1. **세대 웹**: 내 택배 목록, 수령 방식 변경, 로봇 위치(FMS 대역이 보내는 상태)를 확인합니다.
4. **묶음 구성 확인**: `.venv/bin/python -m tools.seed_packages 30` → FMS 터미널에서 층·칸 배정 확인

## 5. 테스트 도구 (`server` 폴더에서 실행)

| 명령 | 설명 |
|---|---|
| `python -m tools.seed_packages 20` | 무작위 동·호수·크기로 접수 + 투입 완료 20건 |
| `python -m tools.set_mode 101-412 --list` | 세대 기본값과 보관 물품 보기 |
| `python -m tools.set_mode 101-412 DIRECT` | 세대 기본값(토글) 변경 → 미적재 물품 일괄 변경 |
| `python -m tools.set_mode 101-412 ROBOT --item <접수번호>` | 물품별 변경 (세대 기본값이 ROBOT일 때만) |
| `python -m tools.fms_stub --arrive 3 --per-item 1 --fail-rate 0.2` | FMS 대역 (도착·배달 시간, 실패 확률 조절) |
| `python -m unittest discover tests` | 서버 단위 테스트 (묶음 구성·접수·수령·수령 방식·배달) |

## 6. 기존 로봇 시뮬레이터(FMS) 연동

1. FMS 대역(`tools.fms_stub`)을 끕니다.
2. 로봇 시뮬레이터가 `protocol.md` 5장의 메시지를 주고받도록 맞춥니다.
   - 받는 토픽: `locker/robot/job`, `locker/robot/bundle`
   - 보내는 토픽: `locker/robot/event`
3. 로봇 시뮬레이터의 기존 형식을 바꾸기 어렵다면, **`server/fms_adapter.py`만 수정**해 형식을 변환합니다. 다른 서버 코드는 바꿀 필요가 없습니다.

## 7. 주요 설정 (`server/config.py`)

| 설정 | 기본값 | 의미 |
|---|---|---|
| `VALID_DONGS`, `FLOORS`, `UNITS_PER_FLOOR` | 101~106, 4, 12 | 단지 규모 (웹은 `web/src/shared/config.ts`도 함께 수정) |
| `SIZE_WEIGHT`, `SIZE_UNITS` | S5/M10/L20kg, S1/M4/L8칸 | 배달 가중치, 공용 박스 칸 수 |
| `BOX_LAYERS`, `LAYER_UNITS`, `ROBOT_MAX_WEIGHT` | 2, 8, 150 | 공용 박스 규격 |
| `MAX_DONGS_PER_BUNDLE`, `AGING_LIMIT_SEC` | 6, 3시간 | 묶음 최대 동 수, 우선 배달 대기시간 |
| `MAX_ACTIVE_JOBS` | 1 | 동시에 진행할 Job 수 (= 로봇 대수) |
| `DEFAULT_MODE`, `MAX_FAIL` | ROBOT, 2 | 세대 기본 수령 방식, 직접 수령 전환 실패 횟수 |
| `PORT_TIMEOUT_SEC`, `SESSION_TTL_SEC` | 60, 600 | 투입 대기 시간, 로그인 세션 유지 시간 |

## 8. 다른 PC·키오스크 단말에서 접속

서버 PC의 IP가 `192.168.0.50`일 때:

- 웹 키오스크 단말: 브라우저에서 `http://192.168.0.50:4173/input`으로 접속합니다. 브로커 주소는 접속한 호스트의 9001 포트로 자동 설정됩니다.
- 다른 PC에서 서버나 도구를 실행할 때: 환경변수 `LOCKER_BROKER_HOST=192.168.0.50`을 설정합니다.
- 웹을 다른 브로커에 붙일 때: `web/.env`에 `VITE_BROKER_URL=ws://192.168.0.50:9001`을 넣습니다.
- 키오스크 번호를 구분하려면 `/input?id=INPUT-02`처럼 접속합니다.

## 9. 문제 해결

| 증상 | 해결 |
|---|---|
| 웹 상단에 "서버 연결 끊김" | 브로커가 9001(WebSocket)로 떠 있는지 확인. `broker/mosquitto.conf`로 실행했는지 확인 |
| `Address already in use` (1883) | 다른 Mosquitto가 실행 중. `brew services stop mosquitto` 또는 해당 프로세스 종료 |
| 접수 버튼을 눌러도 응답 없음 | `server.py`가 실행 중인지, 서버 로그에 "브로커 연결됨"이 찍혔는지 확인 |
| 로그인 실패 | 아이디는 `101-412` 형식, 비밀번호 `1234`. 처음부터 다시 하려면 `python server.py --reset` |
| `ModuleNotFoundError` | `server/.venv`의 Python으로 실행했는지 확인 (2장) |
| macOS에서 `npm run dev`/빌드가 매우 느림 | iCloud 동기화 문제. 2장의 안내 참고 |
>>>>>>> 25a5cd1 (1031_makerton_v1)
