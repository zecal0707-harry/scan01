# Scanner Project - 개발 노트

## 프로젝트 구조

```
scanner/
├── common/           # 공통 모듈 (logging, config, models)
├── scanner/          # 스캐너 모듈 (검색, 인덱싱)
├── downloader/       # 다운로더 모듈
├── ui/               # React UI (Vite)
├── out/              # 인덱스 파일 출력 디렉토리
│   └── required/     # 인덱스 JSON 파일들
└── servers.txt       # 서버 설정 파일
```

## 실행 방법

### 1. 백엔드 서버 시작
```bash
cd scanner
python -m scanner.cli --mode serve --out out --server-file servers.txt --http-port 8081
```

### 2. UI 개발 서버 시작
```bash
cd scanner/ui
npm run dev
```

### 3. 접속
- UI: http://localhost:5173
- API: http://localhost:8081

---

## 주요 개념

### 검색 모드 (Search Mode)

| 모드 | 설명 | 속도 |
|------|------|------|
| `cache` | 인덱스 JSON 파일에서 검색 | 즉시 (밀리초) |
| `direct` | 서버 폴더를 직접 탐색 | 느림 (초~분) |
| `both` | cache 먼저 → 없으면 direct | 자동 |

### 인덱스 관리 (Index Management)

| 기능 | 설명 |
|------|------|
| `Bootstrap` | 서버 전체 탐색하여 인덱스 새로 생성 |
| `Update` | visited 기록 기반 증분 업데이트 (새 경로만 탐색) |

---

## 데이터 구조

### 폴더 구조 (가변 깊이)
```
.../class.../wafer_recipe/lot/film_recipe/date(8자리)/
```

예시:
```
auto scan data/CLN/BS/CN2T_CLN_METALDEP1_TEST/CN2T6800/VBMQ_CLN_POLY_GATE_240929/20240222/
              ^^^^    ^^^^^^^^^^^^^^^^^^^^^^^  ^^^^^^^^  ^^^^^^^^^^^^^^^^^^^^^^^^  ^^^^^^^^
              class   wafer_recipe             lot       film_recipe               date
```

### 인덱스 파일

| 파일 | 용도 |
|------|------|
| `{server}_lots_index.json` | lot 이름 → lot 경로 목록 매핑 |
| `{server}_films_index.json` | lot 경로 → film/date 경로 목록 매핑 |
| `{server}_visited.json` | 방문한 경로 기록 (Update용) |
| `{server}_Full.json` | 메타데이터 |

---

## API 엔드포인트

### 검색
- `POST /v1/search/cache` - 인덱스 검색
- `POST /v1/search/direct` - 서버 직접 탐색

### 인덱스 관리
- `POST /v1/index/bootstrap` - 전체 재인덱싱
- `POST /v1/index/update` - 증분 업데이트
- `GET /v1/index/status` - 인덱스 상태 조회

### 다운로드
- `POST /v1/download` - 선택한 항목 다운로드

### 기타
- `GET /health` - 서버 상태 확인
- `GET /v1/servers` - 서버 목록

---

## 모듈 Import 주의사항

`scanner/scanner/` 및 `scanner/downloader/` 모듈에서 `common` 모듈을 import할 때:

```python
# 잘못된 방식 (작동 안함)
from scanner.common.config import read_server_list

# 올바른 방식
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.config import read_server_list
```

이 패턴은 이미 모든 파일에 적용되어 있음.

---

## 다운로드 폴더 명명 규칙

| 원본 | 다운로드 폴더명 |
|------|----------------|
| film 데이터 | `{film}_spectrum` |
| recipe 데이터 | `{recipe}_filmRecipe` |

예시:
- `VBMQ_CLN_POLY_GATE_240929` → `VBMQ_CLN_POLY_GATE_240929_spectrum`
- recipe → `{recipe_name}_filmRecipe`

---

## 테스트 데이터

### Cache 검색 가능 (films_index에 있음)
- AHNL4204, AKQL1994, AMDV7352, AJ2P3541, AQRQ4114

### Direct 검색만 가능 (lots_index에만 있음)
- CN2T6800, BC6C2560BW, CW0N8314, CYHS6307, EBUB2713DY

---

## 트러블슈팅

### "ECONNREFUSED 127.0.0.1:8081"
- 원인: 백엔드 서버가 실행되지 않음
- 해결: `python -m scanner.cli --mode serve ...` 실행

### "ModuleNotFoundError: No module named 'scanner.common'"
- 원인: Python path 문제
- 해결: 각 모듈 파일 상단에 sys.path.insert 추가 (이미 적용됨)

### UI에서 검색 결과 없음
- cache 모드: films_index.json에 데이터가 있는지 확인
- direct 모드: lots_index.json에 데이터가 있는지 확인
- Bootstrap 실행하여 인덱스 재생성

---

## 변경 이력

### 2026-01-11 (3)
- Scan 인덱스 성능 대폭 개선 (10만개+ 데이터 대응)
  - os.scandir() 사용으로 디렉토리 탐색 최적화
  - FTP 병렬 탐색 (BFS + ThreadPoolExecutor)
  - 진행률 로깅 (1000개마다 진행 상황 표시)
  - 증분 업데이트 시 새 film 항목도 감지
- policy.py에 Scan 인덱스 튜닝 상수 추가
  - `SCAN_INDEX_MAX_WORKERS`: 병렬 처리 worker 수 (기본 16)
  - `SCAN_INDEX_BATCH_SIZE`: 진행률 로깅 주기 (기본 1000)
  - `SCAN_INDEX_MAX_DEPTH`: 최대 탐색 깊이 (기본 15)

### 2026-01-11 (2)
- Film 인덱스 성능 대폭 개선 (2만개 폴더 대응)
  - 증분 업데이트: 새 폴더만 처리, 기존 인덱스 재사용
  - 병렬 처리 강화: 최대 32 workers (policy.py에서 조정 가능)
  - 진행률 로깅: 500개마다 진행률/속도/ETA 표시
  - os.scandir() 사용으로 로컬 폴더 목록 조회 최적화
- policy.py에 Film 인덱스 튜닝 상수 추가
  - `FILM_INDEX_MAX_WORKERS`: 병렬 처리 worker 수 (기본 32)
  - `FILM_INDEX_BATCH_SIZE`: 진행률 로깅 주기 (기본 500)
  - `FILM_INDEX_SKIP_EXISTING`: 증분 업데이트 시 기존 폴더 스킵 여부

### 2026-01-11
- 검색 모드 용어 변경: local→cache, server→direct
- Index Management UI 추가 (Bootstrap, Update, Status)
- 증분 업데이트 기능 구현 (visited.json 기반)
- 모듈 import 경로 문제 수정

### 2026-01-10
- 가변 깊이 폴더 구조 지원 (8자리 date 폴더 기반 파싱)
- 다운로드 폴더 명명 규칙 변경 (_spectrum, _filmRecipe)
- UI에서 직접 다운로드 기능 추가
- Enter 키로 검색 실행

---

## 연락처

문의사항은 프로젝트 저장소 Issues에 등록해주세요.
