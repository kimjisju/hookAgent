import sys
import json
import datetime
import os
import urllib.request
import urllib.error

# 로그 파일 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "..", "log", "claude_audit_log.txt")
SERVER_URL = os.environ.get("HOOK_AGENT_SERVER_URL", "http://127.0.0.1:8765")
EVENT_ENDPOINT = f"{SERVER_URL.rstrip('/')}/api/hook-event"
HTTP_TIMEOUT = int(os.environ.get("HOOK_AGENT_HTTP_TIMEOUT", "3700"))

def log_event(event_type, data):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n[{timestamp}] === {event_type} ===\n")
        f.write(json.dumps(data, indent=2, ensure_ascii=False))
        f.write("\n" + "="*50 + "\n")

def main():
    try:
        # 1. Claude로부터 JSON 데이터 읽기
        input_data = json.load(sys.stdin)
        event_name = input_data.get("hook_event_name")
        
        # RAW 데이터 기록 (항상 최상단에 기록)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n\n=== [RAW INPUT: {event_name}] ===\n")
            f.write(json.dumps(input_data, indent=2, ensure_ascii=False))
            f.write(f"\n")
        # if event_name == "UserPromptSubmit":
        #     log_event("사용자 입력 (USER INPUT)", {"prompt": input_data.get("prompt")})
        
        # elif event_name in ["PreToolUse", "PostToolUse"]:
        #     audit_data = {
        #         "이벤트": event_name,
        #         "도구명": input_data.get("tool_name"),
        #         "인자(Input)": input_data.get("tool_input", {}),
        #         "결과(Result)": input_data.get("tool_result", "N/A"),
        #         # 다양한 키 이름에 대응 (thought, thinking 등)
        #         "추론(Thought)": input_data.get("thought") or input_data.get("thinking") or "N/A"
        #     }
        #     log_event(f"도구 단계 ({event_name})", audit_data)
        # elif event_name == "Stop":
        #     # Stop 이벤트의 'reason'이 클로드의 최종 대답인 경우가 많습니다.
        #     log_event("클로드 최종 응답 및 종료 (STOP)", {
        #         "최종 답변/이유(Reason)": input_data.get("reason", "N/A"),
        #         "추론(Thought)": input_data.get("thought") or "N/A"
        #     })
        
        hook_response = {}
        try:
            request = urllib.request.Request(
                EVENT_ENDPOINT,
                data=json.dumps(input_data, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
                payload = json.loads(response.read().decode("utf-8"))
                hook_response = payload.get("hook_response", {})
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ConnectionError):
            hook_response = {}

        # 3. 중요: 원본 데이터를 그대로 다시 출력하여 Claude의 정상 동작을 보장함
        print(json.dumps(hook_response))

    except Exception as e:
        # 에러 발생 시에도 Claude가 멈추지 않도록 빈 JSON 출력
        print(json.dumps({}))

if __name__ == "__main__":
    main()


# import sys
# import json
# import datetime
# import os

# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# LOG_FILE = os.path.join(BASE_DIR, "..", "log", "claude_audit_log.txt")

# def log_event(event_type, data):
#     timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#     with open(LOG_FILE, "a", encoding="utf-8") as f:
#         f.write(f"\n[{timestamp}] === {event_type} ===\n")
#         f.write(json.dumps(data, indent=2, ensure_ascii=False))
#         f.write("\n" + "="*50 + "\n")

# def main():
#     try:
#         input_data = json.load(sys.stdin)
#         event_name = input_data.get("hook_event_name")
        
#         # RAW 데이터 기록 (항상 최상단에 기록)
#         with open(LOG_FILE, "a", encoding="utf-8") as f:
#             f.write(f"\n\n=== [RAW INPUT: {event_name}] ===\n")
#             f.write(json.dumps(input_data, indent=2, ensure_ascii=False))
#             f.write(f"\n")
#         if event_name == "UserPromptSubmit":
#             log_event("사용자 입력 (USER INPUT)", {"prompt": input_data.get("prompt")})
        
#         elif event_name in ["PreToolUse", "PostToolUse"]:
#             audit_data = {
#                 "이벤트": event_name,
#                 "도구명": input_data.get("tool_name"),
#                 "인자(Input)": input_data.get("tool_input", {}),
#                 "결과(Result)": input_data.get("tool_result", "N/A"),
#                 # 다양한 키 이름에 대응 (thought, thinking 등)
#                 "추론(Thought)": input_data.get("thought") or input_data.get("thinking") or "N/A"
#             }
#             log_event(f"도구 단계 ({event_name})", audit_data)
#         elif event_name == "Stop":
#             # Stop 이벤트의 'reason'이 클로드의 최종 대답인 경우가 많습니다.
#             log_event("클로드 최종 응답 및 종료 (STOP)", {
#                 "최종 답변/이유(Reason)": input_data.get("reason", "N/A"),
#                 "추론(Thought)": input_data.get("thought") or "N/A"
#             })
        
#         # Claude에게 정상 응답
#         print(json.dumps({}))
# #    50    except Exception as e:
#         print(json.dumps({}))

# if __name__ == "__main__":
#     main()
