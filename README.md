# engteacher

Claude Code에 입력한 문장을 교정·번역해 별도 터미널 viewer 또는 창(GUI)에 보여주는 영어 튜터.
요구사항은 [AGENTS.md](AGENTS.md) 참고.

## 동작 구조

```
Claude Code 프롬프트 제출
  └─ UserPromptSubmit hook (async, 세션 지연 없음)
       bin/engteacher-hook
         ├─ input_filter : slash/bash 명령, 코드, URL·경로, 짧은 답변, 긴 붙여넣기 제외
         ├─ transcript   : 같은 세션의 최근 대화 6개를 맥락으로 추출
         ├─ tutor        : 격리된 `claude -p` (기본 Haiku) 또는 `codex exec` 호출 (`model.json` 의 provider)
         └─ store        : ~/.local/state/engteacher/lessons.jsonl 에 추가
bin/engteacher-view  ── lessons.jsonl 을 tail -f 처럼 읽어 표시
bin/engteacher-gui   ── 같은 기록을 별도 창(Tkinter)에 표시
```

- 영어 입력: 문법·어휘 교정, 대안 표현, IPA 발음 표기, 예문
- 한국어 입력: 맥락을 반영한 영어 번역, 대안 표현, 어휘, 예문
- 메인 Claude 세션의 context와 응답에는 영향 없음 (hook stdout 출력 없음)

## 설치

Python 3.10+ 필요 (macOS 기본 `/usr/bin/python3` 3.9는 불가).

```sh
bin/engteacher-install --dry-run   # 변경 diff만 확인
bin/engteacher-install             # diff 확인 후 y 입력 시 적용
bin/engteacher-install --python /opt/homebrew/bin/python3   # hook용 Python 직접 지정
bin/engteacher-install --uninstall --dry-run   # 제거 diff만 확인
bin/engteacher-install --uninstall             # 제거 (교정 기록은 남김)
```

- PATH의 `python3`가 3.10 미만이면 중단하고 `--python` 지정을 요구함
- 적용 전 `settings.json.engteacher-backup-<시각>` 백업 생성, 파일 권한 유지, 원자적 교체
- 이미 등록돼 있으면 아무것도 하지 않고, checkout 경로가 바뀌었으면 기존 항목을 갱신 (중복 추가 없음)
- 확인 대기 중 settings.json이 바뀌면 덮어쓰지 않고 중단
- `--uninstall`: engteacher 항목만 제거, 같은 group의 다른 hook은 유지, 비게 된 group·배열·`hooks` 객체 정리
- 적용·제거 후 실행 중인 Claude Code 세션은 재시작 권장

스크립트가 추가하는 항목 (`hooks.UserPromptSubmit` 배열 끝):

```json
{
  "hooks": [
    {
      "type": "command",
      "command": "ENGTEACHER_PYTHON=/opt/homebrew/bin/python3 /path/to/engteacher/bin/engteacher-hook",
      "timeout": 120,
      "async": true
    }
  ]
}
```

## 사용

별도 터미널 pane에서 viewer 실행:

```sh
bin/engteacher-view            # 최근 5개 표시 후 새 기록 대기
bin/engteacher-view -n 20      # 최근 20개부터
bin/engteacher-view --no-follow
```

또는 별도 창으로 실행 (Tkinter 필요, Homebrew Python은 `brew install python-tk@3.14` 처럼 버전에 맞춰 설치):

```sh
bin/engteacher-gui &           # 최근 20개 표시 후 새 기록 대기
bin/engteacher-gui -n 50
bin/engteacher-gui --topmost --font-size 16   # 이번 실행만 저장된 설정 대신 사용
```

- 설정 창: 상태줄 `설정…` 버튼 또는 macOS 앱 메뉴 Settings(`Cmd-,`)
  - 항상 위에 표시 (Always on top)
  - 글자 크기 (9 ~ 32)
  - 튜터 제공자·모델: 목록(`haiku` / `sonnet` / `opus` / `fable`)에서 선택하거나 전체 모델 이름 입력
- 화면 설정은 `$ENGTEACHER_HOME/gui.json`, 모델 설정은 `$ENGTEACHER_HOME/model.json` 에 저장되어 다음 실행에도 유지
- 모델 변경은 hook이 매 입력마다 `model.json` 을 읽으므로 다음 입력부터 적용 (Claude Code 재시작 불필요)
- 기록 1건씩 카드로 표시. 시간순으로 정렬되며 최신 기록이 마지막 번호 (`20 / 20`)
  - 이동: `◀` / `←` 이전 기록, `▶` / `→` 다음 기록, `최신` / `End` 최신 기록
  - 최신 카드를 보고 있을 때만 새 기록으로 이동 (이전 카드를 읽는 중이면 위치 유지, 개수만 갱신)
  - 카드 내용이 창보다 길면 카드 안에서만 스크롤
- 종료: 창 닫기, `Cmd-W`, 실행한 터미널에서 `Ctrl-C`

## 설정 (환경변수)

| 변수 | 기본값 | 의미 |
|---|---|---|
| `ENGTEACHER_HOME` | `~/.local/state/engteacher` | 기록·오류 로그·GUI 설정 위치 |
| `ENGTEACHER_MODEL` | provider 기본값 | 튜터 모델. 설정하면 `model.json` 의 모델보다 우선 |
| `ENGTEACHER_CLAUDE_BIN` | `claude` | claude 실행 파일 |
| `ENGTEACHER_CODEX_BIN` | `codex` | codex 실행 파일 |
| `ENGTEACHER_TIMEOUT_SEC` | `90` | 튜터 호출 제한 시간 |
| `ENGTEACHER_CONTEXT_MESSAGES` | `6` | 맥락으로 쓸 최근 대화 수 |
| `ENGTEACHER_CONTEXT_CHARS` | `600` | 대화 1개당 최대 글자 수 |
| `ENGTEACHER_MAX_PROMPT_CHARS` | `2000` | 이보다 긴 입력은 붙여넣기로 보고 제외 |
| `ENGTEACHER_PYTHON` | `python3` | 런처가 사용할 Python |

## 운영 참고

- 비용·지연 (claude): 입력 1건당 Haiku 호출 1회, 약 6 ~ 11초, list price 기준 약 $0.004 (Claude 구독 사용량에서 차감)
- 비용·지연 (codex): `gpt-6-luna` 기준 약 6 ~ 11초, 1건당 약 19k tokens (codex 기본 system prompt 포함, ChatGPT 구독 사용량에서 차감)
- 기록 파일: 원문 프롬프트가 평문으로 저장되며 권한 `0600`. 자동 rotation 없음 (1건 약 2KB)
- 실패 시: 세션에는 영향 없고 `errors.log` 에 한 줄 기록
- 재귀 방지: 튜터 프로세스에 `ENGTEACHER_ACTIVE=1` 설정 + `--restricted` 로 user hook 미로딩
- codex 격리: `--ignore-user-config` (MCP·notify·profile 미로딩), `--disable hooks`, `--disable plugins`, `--sandbox read-only`, `--ephemeral`
- codex 한계: 전역 `~/.codex/AGENTS.md` 는 끌 수 있는 옵션이 없어 함께 로딩됨. 튜터 규칙을 developer instructions로 넣고 AGENTS.md를 무시하도록 지시해 영향 최소화
- 한계: 텍스트 입력만 받으므로 실제 발음 교정은 불가. IPA 표기로 대신함

## 테스트

```sh
python3 -m unittest discover -s tests -t .
```

## 모델 설정 파일 (`model.json`)

```json
{
  "provider": "claude",
  "providers": {
    "claude": { "model": "haiku" },
    "codex": { "model": "gpt-6-luna" }
  }
}
```

- 적용 순서: `ENGTEACHER_MODEL` 환경변수 → `model.json` → provider 기본 모델
- provider별 section을 따로 두어 provider를 바꿔도 다른 provider의 모델 값은 유지
- 알 수 없는 provider나 잘못된 모델 이름은 기본값으로 대체
- 지원 provider: `claude` (기본 `haiku`), `codex` (기본 `gpt-6-luna`)
- provider 추가 (pi 예정): `engteacher/model_settings.py` 의 `PROVIDERS` 항목 + `engteacher/tutor_<provider>.py` backend (`build_command`, `extract_lesson`) + `tutor.py` 의 `_BACKENDS` 등록
