# 카드 노트 (저장한 카드 복습) 설계

- 상태: 승인된 설계
- 대상: GUI 뷰어 (`bin/teacherlang-gui`)만. 터미널 뷰어는 변경 없음
- 범위: 카드 저장/해제, 저장한 카드만 넘겨보는 노트 모드
- 범위 밖: 메모 입력, Markdown 등 파일 내보내기

## 1. 화면과 동작

```
 전체  노트                          ☆   ⚙
──────────────────────────────────────────
 ✎ 교정               13:04:00 · teacherlang
 원문   I has a apple
 개선   I have an apple
 ...
──────────────────────────────────────────
                 ‹  3 / 20  ›          최신
```

- 모드 탭과 저장 버튼은 카드 위 도구줄에 배치. 하단 탐색줄은 이동만 담당
- 대안은 카드 맨 아래 `대안 ▸ 2` 제목을 클릭해 펼치고 접음 (하단 버튼 없음)
- 버튼은 테두리 없는 텍스트 버튼 (`teacherlang/gui_widgets.py` 의 `FlatButton`). 상태줄은 오류가 있을 때만 표시

### 저장/해제

- `☆` 버튼 또는 `s` 키 (한글 2벌식 입력 상태의 `ㄴ` 포함): 현재 카드를 저장. 저장 상태면 버튼이 노란 `★`, 다시 누르면 해제
- 전체 모드와 노트 모드에서 같은 버튼 사용

### 모드 전환

- `전체` / `노트` 탭 또는 `n` 키 (한글 입력 상태의 `ㅜ` 포함). Control·Command·Option 과 함께 누르면 무시
- 노트 모드: 저장한 카드만 `time` 기준 시간순으로 표시. 위치 표시는 `노트 2 / 7`
- 전체 모드 위치는 모드를 오가도 유지
- 노트 모드 진입 시 노트 목록을 다시 구성. 직전에 보던 노트가 아직 저장돼 있으면 그 카드, 아니면 최신 노트 표시
- 노트 모드 중 도착한 새 기록은 전체 목록에만 추가, 노트 화면은 변화 없음
- 기존 단축키(`←` `→` `End`, 이전/다음/최신 버튼)는 현재 모드의 목록에 적용

### 노트 모드에서 해제

- 카드를 즉시 제거하지 않고 `☆` 상태로만 표시. 다음 노트 모드 진입 때 목록에서 빠짐
- 이유: 실수로 해제해도 바로 다시 저장할 수 있고, 넘기던 번호가 갑자기 바뀌지 않음

### 빈 노트

- 카드 영역에 `저장한 카드가 없습니다. ☆ 버튼이나 s 키로 카드를 저장하세요.` 표시

## 2. 구성 요소와 데이터 흐름

### 새 파일

- `teacherlang/notes.py` — `NoteStore`, `NotesError`, `lesson_key`
  - 위치: `$TEACHERLANG_HOME/notes.json`
  - 형식: `{"notes": [기록, ...]}` (저장 순서, `lessons.jsonl` 레코드 전체 복사)
  - 카드 식별: `lesson_key(record) = (time, session_id, original)`. 기록에 고유 ID가 없어 세 값을 조합
  - `load() -> list[dict]`, `is_saved(record)`, `save(record)`, `remove(record)`
  - `save`/`remove`는 `notes.lock` 잠금(기존 `archive.log_lock` 재사용) 안에서 파일을 다시 읽어 반영한 뒤 `write_json_atomic` 으로 기록. 창 2개를 띄워도 서로 덮어쓰지 않음
  - 같은 카드 중복 저장은 1건으로 유지
- `teacherlang/card_browser.py` — `CardBrowser` (Tk 의존 없음)
  - 전체 목록 `CardDeck`, 노트 목록 `CardDeck`, 현재 모드 보유
  - `add_lessons()`, `set_mode()`, `toggle_mode()`, `toggle_saved()`, `current()`, `is_current_saved()`, `can_save()`, `notes_error`, 현재 목록 `deck`
  - 시작 시 노트 파일을 한 번 읽어 전체 모드의 저장 상태 표시에 사용

### 수정 파일

- `teacherlang/card_deck.py`: 지정한 위치로 이동하는 `move_to(index)` 공개 (노트 모드 재진입 시 보던 카드 복원)
- `teacherlang/config.py`: `notes_path` 속성 추가
- `teacherlang/gui.py`: 카드 위 도구줄에 `전체` / `노트` 탭과 `☆` 버튼, `s`·`n` 키 바인딩 추가. 판단은 `CardBrowser` 에 위임하고 창은 그리기만 담당
- `README.md`: 노트 기능 설명 추가

### 흐름

```
poll        → browser.add_lessons() → 전체 목록에 추가 (노트 목록 불변)
s / ☆       → browser.toggle_saved() → NoteStore.save/remove → 버튼 표시 갱신
n / 노트    → browser.toggle_mode()  (모든 모드 전환 때 NoteStore.load() 로 다시 읽기)
               └ 노트 모드 진입: NoteStore.load() → time 기준 정렬 → 노트 목록 재구성
                 직전 노트가 남아 있으면 그 카드, 없으면 최신 노트
```

### 키 바인딩 범위

- `s`, `n` 도 기존 `←` `→` `End` 처럼 root 창에만 바인딩. 설정 창 입력 중에는 동작하지 않음

## 3. 오류 처리

| 상황 | 동작 |
|---|---|
| `notes.json` 없음 | 빈 노트로 처리 |
| 손상된 JSON, 최상위가 객체 아님, `notes` 가 목록 아님, 읽기 실패 | `NotesError`. 파일은 덮어쓰지 않음. 하단 안내 줄에 `노트 파일을 읽을 수 없습니다: <경로>`, 저장 버튼 `☆` 으로 비활성화 (저장 상태를 알 수 없으므로), 노트 모드 카드 영역에 같은 안내와 원인. 다음 모드 전환 때 다시 읽기 |
| `notes` 안의 객체가 아닌 항목 | 표시에서는 제외, 저장 시에는 그대로 보존 |
| 쓰기 실패 (디스크 부족, 권한) | 오류 창 표시 (설정 저장 실패와 같은 방식). 버튼은 실제 저장 상태 유지 |
| 파일 권한 | 원문 프롬프트가 들어가므로 `0600` (`mkstemp` 기본값, 테스트로 확인) |

- 기존 `read_json_object` 는 손상된 파일을 빈 값으로 읽으므로 노트에는 사용하지 않음. 손상 파일을 빈 목록으로 읽은 뒤 저장하면 모든 노트가 사라지기 때문

## 4. 테스트

- `tests/test_notes.py`
  - 파일 없음 → 빈 목록
  - 저장 → 해제 왕복, 중복 저장 시 1건
  - 손상 파일 → `NotesError`, 파일 내용 불변
  - 다른 writer 가 추가한 노트 보존
  - 객체가 아닌 항목 보존, 파일 권한 `0600`
- `tests/test_card_browser.py`
  - 모드 전환, 노트 시간순 정렬
  - 새 기록이 노트 목록에 영향 없음
  - 노트 모드에서 해제한 카드는 재진입 전까지 유지
  - 노트 모드 재진입 시 직전 카드 복원, 없으면 최신 노트
  - `NotesError` 발생 시 저장 불가 상태 전달, 파일 복구 후 모드 전환으로 해제
- `tests/test_card_deck.py`: 위치 지정 이동 메서드
- 수동 확인: 임시 `TEACHERLANG_HOME` 으로 실제 Tk 창 스모크 테스트와 스크린샷
