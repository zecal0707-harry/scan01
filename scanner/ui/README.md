# UI (Scanner-only)
- Vite + React + TS 전제. `/scanner` 프록시를 통해 `http://127.0.0.1:8081`에 연결합니다.
- Downloader API는 사용하지 않으며, 검색 결과를 JSON으로 Export 후 CLI ingest를 수행합니다.

핵심 파일:
- `src/App.tsx`: 검색/선택/Export UI, recipe 다중 시 “two+” 배지.
- `src/main.tsx`: React 엔트리.
- `vite.config.ts`: `/scanner` 프록시 예시 포함.
