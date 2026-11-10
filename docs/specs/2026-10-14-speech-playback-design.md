# 개선 문장 음성 재생 설계

- 상태: 승인된 설계
- 대상: GUI 뷰어 (`bin/teacherlang-gui`)만. hook·터미널 뷰어는 변경 없음
- 범위: 카드의 `개선` 문장을 OpenAI TTS로 생성해 재생. 수동 재생 버튼, 자동 재생 옵션
- 범위 밖: 단축키, 예문·대안·어휘 재생, 다른 TTS 제공자, macOS 외 플랫폼의 재생

## 1. 화면과 동작

```
 전체  노트              듣기  내보내기  ☆   ⚙
──────────────────────────────────────────────
 ✎ 교정                 13:04:00 · teacherlang
 원문   I has a apple
 개선   I have an apple
```

### 재생 버튼

- 위쪽 도구줄 `내보내기` 왼쪽에 `듣기` 텍스트 버튼 (`FlatButton`)
- 단축키 없음
- 버튼 표시
  - 대기: `듣기`
  - 생성 중: `불러오는 중…` (비활성 색)
  - 재생 중: `중지` (누르면 재생 중지)
- 읽을 문장이 없는 카드에서는 비활성

### 자동 재생

- 설정 창 체크박스 `새 기록 자동 재생`, 기본값 꺼짐
- 새 기록 도착으로 화면 카드가 그 기록으로 바뀔 때만 재생. 이전 카드를 읽는 중이거나 노트 모드면 재생 안 함
- 시작 시 불러오는 과거 기록은 재생 안 함
- 한 번에 여러 건이 도착하면 화면에 표시되는 마지막 1건만 재생

### 재생 규칙

- 새 재생 요청, 카드 이동, 모드 전환 시 이전 재생 중지. 버튼 상태는 항상 보고 있는 카드 기준
- 창 종료 시 재생 프로세스 종료

### 읽을 문장

- `lesson.improved` 에서 코드 자리표시자(`{A}`, `{AB}` 등) 제거 후 공백 정리
  - 기록에 원래 코드가 남아 있지 않아 복원 불가
  - 예: `remove the {A} section` → `remove the section`
  - 예: `I fixed {A}, then {B}.` → `I fixed, then.`
- 제거 결과가 빈 문자열이면 읽을 문장 없음

### 음성

- 모델 `gpt-4o-mini-tts` 고정
- 지시문 고정: 또렷한 미국식 영어 발음, 보통 속도
- 음성: 설정 창에서 선택, 기본 `marin`
  - 목록 (OpenAI 가이드 2026-10-12 확인, 13종): `alloy` `ash` `ballad` `coral` `echo` `fable` `nova` `onyx` `sage` `shimmer` `verse` `marin` `cedar`
- 출력 형식 MP3

### macOS 외 환경

- `afplay` (macOS 내장 오디오 재생 명령)가 PATH에 없으면 `듣기` 버튼과 설정 창 `음성` 구역을 표시하지 않음

## 2. 구성 요소와 데이터 흐름

### 새 파일

- `teacherlang/speech_settings.py` — `SpeechSettings`, `load_speech_settings`, `save_speech_settings`, `VOICES`
  - 위치: `$TEACHERLANG_HOME/speech.json`
  - 필드: `api_key` (기본 빈 문자열), `voice` (기본 `marin`), `auto_play` (기본 `false`)
  - 값이 없거나 형식이 틀리면 해당 필드만 기본값 (`gui_settings.py` 와 같은 규칙). 목록에 없는 음성은 기본값
  - 저장은 `write_json_atomic` 재사용. `mkstemp` 가 `0600` 으로 만든 임시 파일로 교체하므로 권한 `0600`
- `teacherlang/speech_text.py` — `spoken_text(record) -> str`
  - 자리표시자 정규식은 `input_filter.py` 의 `_PLACEHOLDER` 를 공개 이름 `PLACEHOLDER` 로 바꿔 재사용
  - 제거 후 연속 공백 1칸으로, 구두점(`,` `.` `!` `?` `;` `:`) 앞 공백 제거, 양끝 공백 제거
- `teacherlang/speech_openai.py` — `synthesize(text, api_key, voice, timeout) -> bytes`, `SpeechError`, `MODEL`, `INSTRUCTIONS`
  - 표준 라이브러리 `urllib.request` 로 `POST https://api.openai.com/v1/audio/speech`
  - 본문: `model`, `voice`, `input`, `instructions`, `response_format: "mp3"`
  - 헤더: `Authorization: Bearer <키>`, `Content-Type: application/json`
  - 제한 시간 20초
- `teacherlang/speech_cache.py` — `SpeechCache`
  - 위치: `$TEACHERLANG_HOME/speech-cache/<sha256>.mp3`
  - 키: 모델·음성·지시문·문장을 이어 붙인 값의 SHA-256. 음성이나 지시문이 바뀌면 새로 생성
  - `get(text, voice) -> Path | None`: 있으면 수정 시각을 현재로 갱신 후 경로 반환
  - `put(text, voice, audio) -> Path`: 원자적 쓰기, 권한 `0600`
  - `prune(max_age_days=30)`: 수정 시각이 30일 지난 `.mp3` 삭제. GUI 시작 시 1회
- `teacherlang/speech_player.py` — `SpeechPlayer` (Tk 의존 없음)
  - 상태: `IDLE`, `LOADING`, `PLAYING`
  - `play(text, settings)`: 진행 중인 재생 중지 → 보관본 있으면 바로 재생, 없으면 백그라운드 스레드에서 생성
  - `stop()`: 재생 프로세스 종료, 진행 중인 생성 결과는 버리도록 표시
  - `poll() -> PlayerEvent | None`: 메인 스레드에서 호출. 생성 결과 수신 시 보관 후 재생 시작, 재생 프로세스 종료 시 `IDLE` 로 전환. 오류는 이벤트로 전달
  - 요청 번호: `play`·`stop` 마다 증가. 스레드 결과의 번호가 현재와 다르면 버림
  - 생성 함수, 보관소, 재생 명령 실행 함수를 생성자 인자로 주입 (테스트에서 가짜로 교체)
- `teacherlang/gui_speech.py` — `SpeechControl`
  - `듣기` 버튼과 `SpeechPlayer` 연결: 버튼 표시 갱신, 재생 중에만 0.1초 간격 `poll`
  - `play_card(record, manual: bool)`, `stop()`, `set_settings(settings)`, `close()`
  - 오류 전달: 수동 재생은 오류 대화상자, 자동 재생은 창에 넘긴 콜백으로 안내 줄 표시
  - 이미 600줄인 `gui.py` 를 키우지 않으려고 분리

### 수정 파일

- `teacherlang/input_filter.py`: `_PLACEHOLDER` → `PLACEHOLDER` (공개 이름)
- `teacherlang/config.py`: `speech_settings_path` (`speech.json`), `speech_cache_dir` (`speech-cache/`) 속성
- `teacherlang/gui.py`
  - 도구줄에 `듣기` 버튼 배치 (`afplay` 있을 때만)
  - 카드를 다시 그릴 때(`_render_card`) 재생 중지와 버튼 활성 상태 갱신
  - 새 기록으로 카드가 바뀌면 자동 재생 설정 확인 후 `play_card(record, manual=False)`
  - 창 종료 시 `SpeechControl.close()`
  - 안내 줄 우선순위: 노트 파일 오류 > 기록 파일 오류 > 음성 오류
- `teacherlang/gui_settings_dialog.py`: `음성` 구역 추가
  - `새 기록 자동 재생` 체크박스
  - `음성` 목록 (읽기 전용 Combobox)
  - `OpenAI API 키` 입력칸 (`show="•"`), Enter·포커스 이동·창 닫기 시 저장
  - 안내 문구: 키 저장 위치와 권한 `0600`
- `gui.py` 의 `SettingsController`: 음성 설정 저장 콜백 추가, 변경 시 `SpeechControl.set_settings()`
- `README.md`: 사용법, 비용, 저장 위치

### 흐름

```
듣기 / 자동 재생
  → spoken_text(record)
  → SpeechPlayer.play()
       ├ 보관본 있음 → afplay 실행 (PLAYING)
       └ 없음 → 스레드: synthesize() (LOADING)
                 → poll(): 보관 → afplay 실행 (PLAYING)
  → poll(): afplay 종료 → IDLE
```

- 음성 설정은 GUI 시작 시 읽고, 설정 창에서 바꿀 때마다 저장·반영. hook 은 읽지 않음

## 3. 오류 처리

| 상황 | 안내 |
|---|---|
| API 키 없음 | 설정에서 OpenAI API 키를 입력하세요 |
| HTTP 401 | API 키가 올바르지 않습니다 |
| HTTP 429 | 사용 한도를 넘었거나 요청이 너무 많습니다 |
| 그 밖의 HTTP 오류 | 음성을 만들지 못했습니다 (HTTP <코드>) |
| 네트워크 오류, 20초 초과 | OpenAI에 연결하지 못했습니다 |
| 보관 파일 쓰기 실패 | 음성 파일을 저장하지 못했습니다 + `OSError` 내용 |
| `afplay` 실행 실패, 0이 아닌 종료 코드 | 음성을 재생하지 못했습니다 |

- 표시 방식
  - 수동 재생: 오류 대화상자 (노트 저장 실패와 같은 방식)
  - 자동 재생: 아래쪽 빨간 안내 줄. 다음 재생 성공 시 제거
- 안내 문구에 API 키와 응답 본문을 넣지 않음. OpenAI 오류 응답에 키 일부가 담길 수 있기 때문
- 자원 관리
  - 재생 프로세스 최대 1개. 중지 시 `terminate()` 후 1초 대기, 남아 있으면 `kill()`
  - 생성 스레드는 데몬 스레드, 20초 제한으로 종료 보장. 취소된 요청은 결과만 버림
  - 창 종료 시 재생 프로세스 정리

## 4. 테스트

- `tests/test_speech_settings.py`: 파일 없음 → 기본값, 형식이 틀린 필드만 기본값, 목록에 없는 음성 → 기본값, 저장 후 권한 `0600`
- `tests/test_speech_text.py`: 자리표시자 제거, 공백·구두점 정리, `improved` 없음·자리표시자만 있음 → 빈 문자열
- `tests/test_speech_openai.py`: 가짜 `urlopen` 으로 요청 URL·헤더·본문 확인, 401·429·500·시간 초과 → `SpeechError` 문구에 키 미포함
- `tests/test_speech_cache.py`: 저장·조회, 음성이 다르면 다른 파일, 조회 시 수정 시각 갱신, 30일 지난 파일만 삭제, 권한 `0600`
- `tests/test_speech_player.py`: 가짜 생성 함수·재생 명령으로
  - 보관본 없음 → `LOADING` → `PLAYING` → `IDLE`
  - 보관본 있음 → 생성 함수 호출 없이 `PLAYING`
  - 생성 중 `stop()` 또는 새 `play()` → 이전 결과 버림
  - 재생 중 `stop()` → 프로세스 종료
  - 생성 오류·재생 실패 → 오류 이벤트
- 기존 테스트 전체 통과
- 수동 확인 (임시 `TEACHERLANG_HOME`)
  - 실제 API 키로 문장 1개 생성·재생 (비용 약 $0.0015)
  - 버튼 상태 전환, 자동 재생, 카드 이동 시 중지, 같은 문장 재생 시 보관본 사용
  - 보관 파일 크기 실측 후 README 반영
