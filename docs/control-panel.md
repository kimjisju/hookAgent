# Control Panel

## 개요

실시간 GUI와 도구 승인 제어는 로컬 컨트롤 서버를 중심으로 동작합니다.

- Claude 훅 이벤트는 [`scripts/auditor.py`](/Users/sh_kim/Library/Mobile%20Documents/com~apple~CloudDocs/workspace/hookAgent/scripts/auditor.py)가 수신합니다.
- 이벤트는 [`scripts/hook_agent_server.py`](/Users/sh_kim/Library/Mobile%20Documents/com~apple~CloudDocs/workspace/hookAgent/scripts/hook_agent_server.py)로 전달됩니다.
- 서버는 웹 GUI를 제공하고, `PreToolUse` 이벤트에서 사용자 승인 결과를 기다립니다.
- 브라우저 GUI는 [`web/index.html`](/Users/sh_kim/Library/Mobile%20Documents/com~apple~CloudDocs/workspace/hookAgent/web/index.html), [`web/app.js`](/Users/sh_kim/Library/Mobile%20Documents/com~apple~CloudDocs/workspace/hookAgent/web/app.js), [`web/styles.css`](/Users/sh_kim/Library/Mobile%20Documents/com~apple~CloudDocs/workspace/hookAgent/web/styles.css)로 구성됩니다.

## 실행

다음 스크립트로 컨트롤 서버와 Claude를 함께 실행할 수 있습니다.

```bash
python3 app.py
```

이 진입점은 다음을 수행합니다.

1. 로컬 컨트롤 서버 실행
2. 브라우저에서 GUI 열기
3. `claude --plugin-dir ./plugins/auditor` 실행
4. Claude 종료 시 서버 프로세스도 함께 종료

## 승인 제어 방식

`PreToolUse` 이벤트가 발생하면 서버는 해당 도구 호출을 승인 대기 상태로 등록합니다. 사용자가 GUI에서 `Yes`를 누르면 도구 실행을 허용하고, `No`를 누르면 도구 실행을 차단합니다.

Claude 훅 응답은 Anthropic Claude Code Hooks 문서의 `PreToolUse` 제어 형식에 맞춰 `hookSpecificOutput.permissionDecision`으로 반환합니다.

공식 문서: [Claude Code Hooks](https://docs.anthropic.com/en/docs/claude-code/hooks)

## 현재 범위

현재 GUI는 다음을 실시간으로 보여줍니다.

- 세션 목록
- 사용자 입력
- 도구 사용 전후 이벤트
- 알림 이벤트
- 최종 응답
- 승인 대기 중인 도구 요청

현재 “추론”은 훅에 직접 노출되지 않으므로, GUI는 plan 텍스트, 도구 입력, 도구 설명, 최종 응답 같은 추론 신호를 간접적으로 보여주는 구조입니다.
