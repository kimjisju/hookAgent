# 현재 구현

## 현재까지 구현 범위

현재 프로젝트는 다음 범위까지 구현되어 있습니다.

- Claude Code에서 사용자 입력과 도구 사용을 추적
- gemini-cli에서 주요 훅 이벤트와 도구 사용을 추적
- Codex CLI에서 주요 훅 이벤트와 도구 사용을 추적
- 프록시 서버(`mitmproxy`)를 통해 외부와의 통신 과정, 특히 LLM과의 통신 과정을 추적
- 로컬 컨트롤 서버와 웹 GUI를 통해 Claude / Gemini 훅 이벤트를 실시간으로 추적
- 로컬 컨트롤 서버와 웹 GUI를 통해 Claude / Gemini / Codex 훅 이벤트를 실시간으로 추적
- Claude의 `PreToolUse`, Gemini의 `BeforeTool`, Codex의 `PreToolUse` 이벤트에서 사용자의 `Yes`/`No` 판단으로 도구 사용을 제어

## 1. Claude Code에서 사용자 입력과 도구 사용을 추적하는 방법

`auditor`는 모든 Claude Code 훅 이벤트에 대해 [`scripts/auditor.py`](/Users/sh_kim/Library/Mobile%20Documents/com~apple~CloudDocs/workspace/hookAgent/scripts/auditor.py)를 실행하게 해서 로그에 저장합니다.

실행 시 다음 명령어를 사용해야 합니다.

```bash
claude --plugin-dir ./plugins/auditor
```

현재는 `--plugin-dir ./plugins/auditor`를 명시하지 않으면 플러그인으로 인식되지 않는 문제가 있습니다. 이 부분은 향후 개선 대상입니다.

훅 설정은 [`plugins/auditor/hooks/hooks.json`](/Users/sh_kim/Library/Mobile%20Documents/com~apple~CloudDocs/workspace/hookAgent/plugins/auditor/hooks/hooks.json)에 있으며, 주요 Claude Code 이벤트에서 `scripts/auditor.py`를 호출합니다.

현재 훅 대상 이벤트는 다음과 같습니다.

- `SessionStart`
- `SessionEnd`
- `UserPromptSubmit`
- `PreToolUse`
- `PostToolUse`
- `Stop`
- `SubagentStop`
- `PreCompact`
- `Notification`

현재 코드 기준으로는 훅 이벤트의 RAW 입력을 계속 기록하면서, 동시에 로컬 컨트롤 서버로 구조화 이벤트를 전송합니다.

구조화 로그는 다음 파일에도 저장됩니다.

- `log/hook_agent_events.jsonl`
- `log/hook_agent_approvals.jsonl`

## 1-2. gemini-cli에서 사용자 입력과 도구 사용을 추적하는 방법

gemini-cli는 extension 형식으로 지원합니다. 확장 루트는 `plugins/gemini-auditor`이며,
Gemini CLI의 `gemini-extension.json` 및 `hooks/hooks.json` 규약을 따릅니다.

훅 설정은 `plugins/gemini-auditor/hooks/hooks.json`에 있으며, 다음 주요 이벤트를
`scripts/gemini_auditor.py`로 전달합니다.

- `SessionStart`
- `SessionEnd`
- `BeforeAgent`
- `AfterAgent`
- `BeforeTool`
- `AfterTool`
- `BeforeModel`
- `AfterModel`
- `BeforeToolSelection`
- `Notification`
- `PreCompress`

`scripts/gemini_auditor.py`는 Gemini 훅 입력을 그대로 기록하고, 로컬 컨트롤 서버로
구조화 이벤트를 전달합니다. `BeforeTool` 이벤트에서는 서버의 승인 결과를 받아
Gemini 훅 응답 형식인 `decision` / `reason`으로 다시 반환합니다.

로컬에서 개발 중인 extension은 다음처럼 연결할 수 있습니다.

```bash
gemini extensions link ./plugins/gemini-auditor
python3 app.py --agent gemini
```

## 1-3. Codex CLI에서 사용자 입력과 도구 사용을 추적하는 방법

Codex는 `hooks.json` 기반 lifecycle hook을 사용합니다. hookAgent는
`plugins/codex-auditor`를 원본 템플릿으로 두고, 실행 시 프로젝트 루트의 `.codex/`
설정으로 동기화해서 사용합니다.

훅 설정은 `plugins/codex-auditor/hooks.json`에 있으며, 다음 주요 이벤트를
`scripts/codex_auditor.py`로 전달합니다.

- `SessionStart`
- `UserPromptSubmit`
- `PreToolUse`
- `PostToolUse`
- `Stop`

`scripts/codex_auditor.py`는 Codex 훅 입력을 그대로 기록하고, 로컬 컨트롤 서버로
구조화 이벤트를 전달합니다. `PreToolUse` 이벤트에서는 서버의 승인 결과를 받아
Codex 훅 응답 형식인 `hookSpecificOutput.permissionDecision`으로 다시 반환합니다.

실행은 다음처럼 할 수 있습니다.

```bash
python app.py --agent codex
```

주의: Codex upstream 구현상 `hooks.json` lifecycle hooks는 현재 Windows에서
지원되지 않아 Linux/macOS에서만 동작합니다.

## 2. 외부와의 통신 과정을 추적하는 방법

외부와의 통신 과정은 `mitmproxy`를 설치한 뒤 프록시를 통해 Claude Code를 실행하여 추적합니다.

실행 전 필요한 환경 변수와 실행 명령은 다음과 같습니다.

```bash
export HTTPS_PROXY=http://127.0.0.1:8080
export NODE_TLS_REJECT_UNAUTHORIZED=0
claude
```

이 방식으로 특히 LLM과의 통신 과정을 관찰할 수 있습니다.

## 현재 구현의 의미

현재 단계의 구현은 아직 4단계 위험 탐지와 제어를 자동으로 수행하는 수준은 아닙니다. 대신 다음을 가능하게 합니다.

- 에이전트가 어떤 사용자 입력을 받았는지 추적
- 에이전트가 어떤 시점에 어떤 도구를 사용하려 했는지 추적
- 에이전트가 외부 LLM 또는 외부 시스템과 어떤 통신을 했는지 추적
- 웹 GUI에서 세션과 이벤트를 실시간으로 관찰
- 도구 실행 전에 사용자가 수동으로 허용 또는 차단

즉, 현재는 "감시와 기록" 단계를 넘어 "실시간 관찰"과 "사용자 승인 기반 제어"까지 구현된 상태입니다.
