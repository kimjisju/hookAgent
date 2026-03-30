# hookAgent

<!-- ![Preview](docs/img/Preview.png) -->

<img src="docs/img/Preview.png", height="200x">

HookAgent는 AI Agent의 사용자 입력, 추론, 도구 사용을 가로채고 감시하여 나쁜 행동을 탐지하고 제한합니다.

## 탐지 과정

1. 사용자 입력에 프롬프트 인젝션 내용이 없는가?
2. 사용자 입력에 따른 정당한 추론인가?
3. 정당한 추론에 따른 정당한 도구 사용인가?
4. 도구 사용 결과가 추론에 부합하는가?

## 사용 방법

```bash
python3 app.py
```

## 문서 목록

- [프로젝트 개요](docs/project-overview.md)
- [현재 구현](docs/current-implementation.md)
- [컨트롤 패널](docs/control-panel.md)
- [로드맵](docs/roadmap.md)
