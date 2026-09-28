# TeacherLang

Claude Code에 입력한 문장을 교정·번역해 별도 터미널 viewer 또는 창(GUI)에 보여주는 영어 튜터.
요구사항은 [AGENTS.md](AGENTS.md) 참고.

## 동작 구조

```
Claude Code 프롬프트 제출
  └─ UserPromptSubmit hook (async, 세션 지연 없음)
       bin/teacherlang-hook
         ├─ input_filter : slash/bash 명령, 코드, URL·경로, 짧은 답변, 긴 붙여넣기 제외
         ├─ transcript   : 같은 세션의 최근 대화 6개를 맥락으로 추출
         ├─ tutor        : 격리된 `claude -p` (기본 Haiku) 또는 `codex exec` 호출 (`model.json` 의 provider)
         └─ store        : ~/.local/state/teacherlang/lessons.jsonl 에 추가 (날짜가 바뀌면 지난 기록 압축 보관)
bin/teacherlang-view  ── lessons.jsonl 을 tail -f 처럼 읽어 표시 (부족한 history는 보관본에서 채움)
bin/teacherlang-gui   ── 같은 기록을 별도 창(Tkinter)에 표시
```

- 영어 입력: 문법·어휘 교정, IPA 발음 표기, 예문
- 한국어 입력: 맥락을 반영한 영어 번역, 어휘, 예문
- 메인 Claude 세션의 context와 응답에는 영향 없음 (hook stdout 출력 없음)

## 설치

Python 3.10+ 필요 (macOS 기본 `/usr/bin/python3` 3.9는 불가).

```sh
bin/teacherlang-install --dry-run   # 변경 diff만 확인
bin/teacherlang-install             # diff 확인 후 y 입력 시 적용
bin/teacherlang-install --python /opt/homebrew/bin/python3   # hook용 Python 직접 지정
bin/teacherlang-install --uninstall --dry-run   # 제거 diff만 확인
bin/teacherlang-install --uninstall             # 제거 (교정 기록은 남김)
```

- PATH의 `python3`가 3.10 미만이면 중단하고 `--python` 지정을 요구함
- 적용 전 `settings.json.teacherlang-backup-<시각>` 백업 생성, 파일 권한 유지, 원자적 교체
- 이미 등록돼 있으면 아무것도 하지 않고, checkout 경로가 바뀌었으면 기존 항목을 갱신 (중복 추가 없음)
- 확인 대기 중 settings.json이 바뀌면 덮어쓰지 않고 중단
- `--uninstall`: teacherlang 항목만 제거, 같은 group의 다른 hook은 유지, 비게 된 group·배열·`hooks` 객체 정리
- 적용·제거 후 실행 중인 Claude Code 세션은 재시작 권장
- 자동 설치 제안: `teacherlang-view` / `teacherlang-gui` 시작 시 hook 항목이 없으면 diff를 보여주고 설치 여부 확인
  - viewer는 터미널 `[y/N]`, GUI는 대화상자. 백그라운드 실행 등 물어볼 수 없는 터미널이면 안내만 출력
  - 거절·실패해도 프로그램은 그대로 실행, 다음 실행 때 다시 확인 (`--no-install-check` 로 생략)
  - hook용 Python은 런처와 같은 규칙 (`TEACHERLANG_PYTHON`, 없으면 PATH의 `python3`)
  - 이미 등록된 항목은 Python·경로가 달라도 그대로 둠 (갱신은 `bin/teacherlang-install`)

스크립트가 추가하는 항목 (`hooks.UserPromptSubmit` 배열 끝):

```json
{
  "hooks": [
    {
      "type": "command",
      "command": "TEACHERLANG_PYTHON=/opt/homebrew/bin/python3 /path/to/teacherlang/bin/teacherlang-hook",
      "timeout": 120,
      "async": true
    }
  ]
}
```

## 사용

별도 터미널 pane에서 viewer 실행:

```sh
bin/teacherlang-view            # 최근 5개 표시 후 새 기록 대기
bin/teacherlang-view -n 20      # 최근 20개부터
bin/teacherlang-view --no-follow
```

또는 별도 창으로 실행 (Tkinter 필요, Homebrew Python은 `brew install python-tk@3.14` 처럼 버전에 맞춰 설치):

```sh
bin/teacherlang-gui &           # 최근 20개 표시 후 새 기록 대기
bin/teacherlang-gui -n 50
bin/teacherlang-gui --topmost --font-size 16   # 이번 실행만 저장된 설정 대신 사용
```

- 설정 창: 오른쪽 위 `⚙` 버튼 또는 macOS 앱 메뉴 Settings(`Cmd-,`)
  - 항상 위에 표시 (Always on top)
  - 글자 크기 (9 ~ 32)
  - 튜터 제공자·모델: 목록(`haiku` / `sonnet` / `opus` / `fable`)에서 선택하거나 전체 모델 이름 입력
  - 기록 보관기간 (0 ~ 365일, 기본 14일, 0이면 삭제 안 함)
- 화면 설정은 `$TEACHERLANG_HOME/gui.json`, 모델 설정은 `$TEACHERLANG_HOME/model.json`, 보관기간은 `$TEACHERLANG_HOME/storage.json` 에 저장되어 다음 실행에도 유지
- 모델 변경은 hook이 매 입력마다 `model.json` 을 읽으므로 다음 입력부터 적용 (Claude Code 재시작 불필요)
- 화면: 위쪽 줄(`전체` `노트` 탭, `☆`, `⚙`), 카드, 아래쪽 줄(`‹ 20 / 20 ›`, `최신`)
  - 테두리 없는 텍스트 버튼. 마우스를 올리면 강조 색, 쓸 수 없으면 흐리게 표시
  - macOS에서는 시스템 배경·글자 색을 따라 다크 모드에서도 어둡게 표시
  - 상태줄 없음. 기록·노트 파일을 읽지 못할 때만 아래쪽에 빨간 안내 줄 표시
- 기록 1건씩 카드로 표시. 시간순으로 정렬되며 최신 기록이 마지막 번호 (`20 / 20`)
  - 카드 제목(교정·번역) 오른쪽에 시각과 프로젝트, 긴 줄은 내용 시작 위치에 맞춰 줄바꿈
  - 이동: `‹` / `←` 이전 기록, `›` / `→` 다음 기록, `최신` / `End` 최신 기록
  - 최신 카드를 보고 있을 때만 새 기록으로 이동 (이전 카드를 읽는 중이면 위치 유지, 개수만 갱신)
  - 카드 맨 아래 `대안 ▸ 2` 제목을 클릭해 대안 표현 펼치기/접기 (`대안 ▾`). 숫자는 대안 개수, 카드 이동 시 다시 접힘, 대안이 없는 기록은 섹션 없음
  - 카드 내용이 창보다 길면 카드 안에서만 스크롤
- 카드 노트: 복습할 카드를 저장해 두고 모아 보기
  - 저장/해제: 오른쪽 위 `☆` 버튼 또는 `s` (저장되면 노란 `★`)
  - 모드 전환: `전체` / `노트` 탭 또는 `n` (선택한 탭은 굵게). 노트 모드는 저장한 카드만 시간순 표시 (`노트 2 / 7`)
  - 노트 모드에서 해제한 카드는 `☆` 로만 바뀌고, 다음 노트 모드 진입 때 목록에서 빠짐 (실수로 해제해도 바로 다시 저장 가능)
  - `$TEACHERLANG_HOME/notes.json` 에 카드 전체를 복사해 저장하므로 기록 보관기간이 지나 원본이 삭제돼도 유지 (권한 `0600`)
  - 노트 파일이 손상되면 덮어쓰지 않고 저장을 막은 뒤 아래쪽 안내 줄에 표시. 파일을 고치거나 옮긴 뒤 모드를 전환하면 다시 읽음
- 종료: 창 닫기, `Cmd-W`, 실행한 터미널에서 `Ctrl-C`

## 설정 (환경변수)

| 변수 | 기본값 | 의미 |
|---|---|---|
| `TEACHERLANG_HOME` | `~/.local/state/teacherlang` | 기록·오류 로그·GUI 설정 위치 |
| `TEACHERLANG_MODEL` | provider 기본값 | 튜터 모델. 설정하면 `model.json` 의 모델보다 우선 |
| `TEACHERLANG_CLAUDE_BIN` | `claude` | claude 실행 파일 |
| `TEACHERLANG_CODEX_BIN` | `codex` | codex 실행 파일 |
| `TEACHERLANG_TIMEOUT_SEC` | `90` | 튜터 호출 제한 시간 |
| `TEACHERLANG_CONTEXT_MESSAGES` | `6` | 맥락으로 쓸 최근 대화 수 |
| `TEACHERLANG_CONTEXT_CHARS` | `600` | 대화 1개당 최대 글자 수 |
| `TEACHERLANG_MAX_PROMPT_CHARS` | `2000` | 이보다 긴 입력은 붙여넣기로 보고 제외 |
| `TEACHERLANG_RETENTION_DAYS` | `storage.json` 값 (기본 `14`) | 지난 날짜 보관본 보관기간(일), 0이면 삭제 안 함. 설정하면 `storage.json` 보다 우선 |
| `TEACHERLANG_PYTHON` | `python3` | 런처가 사용할 Python |

## 운영 참고

- 비용·지연 (claude): 입력 1건당 Haiku 호출 1회, 약 6 ~ 11초, list price 기준 약 $0.004 (Claude 구독 사용량에서 차감)
- 비용·지연 (codex): `gpt-6-luna` 기준 약 7 ~ 12초, 1건당 약 1.4k input tokens (기본 prompt·skills 목록·tool 정의 제외, ChatGPT 구독 사용량에서 차감)
- 기록 파일: 원문 프롬프트가 저장되며 모든 파일 권한 `0600` (1건 약 1.2KB, gzip 압축 시 약 1/3.7)
  - `lessons.jsonl`: 오늘 기록 (평문 JSONL)
  - `lessons-YYYY-MM-DD.jsonl.gz`: 지난 날짜 보관본. 시계가 되돌아가 같은 날짜가 다시 보관되면 `lessons-YYYY-MM-DD.2.jsonl.gz`
  - 로테이션 시점: hook이 기록을 추가할 때 `lessons.jsonl` 의 마지막 수정 날짜가 오늘 이전이면 먼저 보관본으로 압축
  - 삭제: 같은 시점에 보관기간이 지난 보관본 삭제 (보관기간 14일이면 오늘 기준 14일 전 날짜까지 유지)
  - `lessons.lock`: 동시에 끝난 여러 세션의 로테이션·추가를 직렬화
  - 보관본 직접 보기: `gzip -dc lessons-2026-09-27.jsonl.gz`
- 실패 시: 세션에는 영향 없고 `errors.log` 에 한 줄 기록
- 재귀 방지: 튜터 프로세스에 `TEACHERLANG_ACTIVE=1` 설정 + `--restricted` 로 user hook 미로딩
- codex 격리: `--ignore-user-config` (MCP·notify·profile 미로딩), `--disable hooks`, `--disable plugins`, `--sandbox read-only`, `--ephemeral`
- codex prompt 축소: `model_instructions_file` 로 codex 기본 prompt를 튜터 규칙으로 대체, `skills.include_instructions=false` 로 skills 목록 제외, `include_*_instructions=false`·`include_environment_context=false` 로 부가 섹션 제외
- codex tool 제거: `--disable` (`apps`, `shell_tool`, `unified_exec`, `view_image`, `goals`, `multi_agent`, `image_generation`), `web_search="disabled"`, `tools.experimental_request_user_input.enabled=false`
  - code mode(`exec`/`wait`)·multi-agent tool은 모델 카탈로그가 켜므로, `~/.codex/models_cache.json` 의 해당 모델 항목을 복사해 tool 관련 필드만 바꾼 카탈로그(`$TEACHERLANG_HOME/codex-model-catalog.json`)를 `model_catalog_json` 으로 전달
  - 캐시에 모델이 없으면 카탈로그 없이 실행 (일부 tool이 남고 input tokens 약 4.6k)
- codex 한계: 전역 `~/.codex/AGENTS.md` 는 끌 수 있는 옵션이 없어 함께 로딩됨. 튜터 규칙에 AGENTS.md를 무시하라는 지시를 넣어 영향 최소화
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

- 적용 순서: `TEACHERLANG_MODEL` 환경변수 → `model.json` → provider 기본 모델
- provider별 section을 따로 두어 provider를 바꿔도 다른 provider의 모델 값은 유지
- 알 수 없는 provider나 잘못된 모델 이름은 기본값으로 대체
- 지원 provider: `claude` (기본 `haiku`), `codex` (기본 `gpt-6-luna`)
- provider 추가 (pi 예정): `teacherlang/model_settings.py` 의 `PROVIDERS` 항목 + `teacherlang/tutor_<provider>.py` backend (`build_command`, `extract_lesson`) + `tutor.py` 의 `_BACKENDS` 등록
