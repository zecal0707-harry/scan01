# 리팩토링 작업 로그

**작업일**: 2026-01-10
**작업자**: Claude Opus 4.5

---

## 1. 코드 분석 결과

### 발견된 주요 문제점

| 구분 | 문제 | 파일 | 심각도 |
|------|------|------|--------|
| 디버그 코드 | `print()` 문이 프로덕션에 남아있음 | search.py, http_api.py | 높음 |
| 디버그 코드 | 디버그 파일 쓰기 (`debug_*.txt`) | film_index.py, ftp.py | 높음 |
| 중복 코드 | `ServerConfig` 클래스 중복 | models.py, downloader/config.py | 중간 |
| 중복 코드 | `LocalAdapter` 클래스 중복 | fs_local.py, ftp_local.py | 중간 |
| 중복 코드 | `read_server_list` 함수 중복 | scanner/config.py, downloader/config.py | 중간 |
| 중복 코드 | `setup_logger` 함수 중복 | scanner/cli.py, downloader/cli.py | 낮음 |
| 코드 품질 | 중복 import (`import sys` 2회) | ftp.py | 낮음 |
| 스레드 안전성 | 클래스 변수로 설정 공유 | http_api.py | 중간 |
| 에러 핸들링 | 잘못된 regex 패턴 무시 | utils.py, search.py | 중간 |

---

## 2. 수행한 리팩토링 작업

### 2.1 디버그 코드 제거

#### film_index.py (lines 73-85)
```python
# Before
except Exception as e:
    with open("debug_film.txt", "a") as f: f.write(f"DEBUG: NLST glob failed ({e}), fallback\n")
    ...

# After
except Exception:
    # Fallback for servers that don't support NLST globbing
    try:
        all_names = conn.nlst()
    except Exception:
        all_names = []
    ...
```

#### search.py (lines 162, 172-174, 183)
```python
# Before
print(f"DEBUG: Wafer Check | {wafer_name} | {p} | {filters.wafer}")
print("DEBUG: Wafer Mismatch")
print("DEBUG: Wafer Match")
print(f"DEBUG: Film Check | P='{p}' | FoundLocally={p in fidx} | NumFilms={len(lot_films)}")

# After
# 모든 print 문 제거
```

#### http_api.py (line 78, 55-56, 94-95)
```python
# Before
print(f"DEBUG: /v1/search/server BODY={json.dumps(body)}")
with open("out/debug_error.log", "a", encoding="utf-8") as f:
    f.write(f"GET ERROR: {str(e)}\n{traceback.format_exc()}\n")

# After
# print 제거, 파일 쓰기를 logger로 교체
if self.logger:
    self.logger.error(f"GET ERROR: {str(e)}\n{traceback.format_exc()}")
```

#### ftp.py (lines 111-132)
```python
# Before
import sys
import sys  # 중복
with open("debug_ftp.txt", "a") as f: f.write(f"DEBUG: {fn.__name__} failed: {e}\n")

# After
# 중복 import 제거, 파일 쓰기를 logger로 교체
if logger:
    logger.debug(f"list_dirs: {fn.__name__} failed: {e}")
```

---

### 2.2 공통 모듈 생성

새로운 디렉토리 `scanner/common/` 생성:

```
scanner/common/
├── __init__.py
├── models.py      # ServerConfig, SearchFilters, Hit
├── config.py      # read_server_list, DEFAULT_* 상수
├── fs_local.py    # LocalAdapter, list_dirs_local
└── logging.py     # setup_logger, get_logger
```

#### scanner/common/models.py
- `ServerConfig` dataclass (통합)
- `SearchFilters` dataclass
- `Hit` dataclass

#### scanner/common/config.py
- `read_server_list()` 함수 (validation 포함 버전)
- DEFAULT_* 상수들

#### scanner/common/fs_local.py
- `LocalAdapter` 클래스 (통합: `retr_first_n` + `retrbinary`)
- `list_dirs_local()` 함수

#### scanner/common/logging.py
- `setup_logger()` 함수 (통합)
- `get_logger()` 함수

---

### 2.3 기존 모듈 업데이트 (Re-export)

하위 호환성을 위해 기존 모듈에서 공통 모듈을 re-export:

```python
# scanner/scanner/models.py
from scanner.common.models import ServerConfig, SearchFilters, Hit
__all__ = ['ServerConfig', 'SearchFilters', 'Hit']

# scanner/scanner/config.py
from scanner.common.config import read_server_list, DEFAULT_*
__all__ = [...]

# scanner/scanner/fs_local.py
from scanner.common.fs_local import LocalAdapter, list_dirs_local
__all__ = ['LocalAdapter', 'list_dirs_local']

# scanner/downloader/config.py
from scanner.common.models import ServerConfig
from scanner.common.config import read_server_list
__all__ = ['ServerConfig', 'read_server_list']

# scanner/downloader/ftp_local.py
from scanner.common.fs_local import LocalAdapter
__all__ = ['LocalAdapter']
```

---

### 2.4 스레드 안전성 개선 (http_api.py)

```python
# Before - 클래스 변수 사용 (스레드 간 공유)
class APIServer(BaseHTTPRequestHandler):
    cfgs = []
    out_dir = "out"
    logger = None

def make_server(cfgs, out_dir, logger, ...):
    APIServer.cfgs = cfgs
    APIServer.out_dir = out_dir
    APIServer.logger = logger

# After - Factory 패턴 (closure로 캡처)
def create_handler(cfgs: List[ServerConfig], out_dir: str, logger):
    class APIHandler(BaseHTTPRequestHandler):
        # cfgs, out_dir, logger를 closure로 캡처
        def do_GET(self):
            for c in cfgs:  # closure 변수 사용
                ...
    return APIHandler

def make_server(cfgs, out_dir, logger, ...):
    handler_class = create_handler(cfgs, out_dir, logger)
    srv = ThreadingHTTPServer((addr, port), handler_class)
    return srv
```

추가 개선:
- `_parse_search_filters()` 헬퍼 함수로 중복 코드 제거
- `log_message()` 오버라이드로 HTTP 로깅 통합

---

### 2.5 Regex 에러 핸들링 개선

#### scanner/scanner/utils.py
```python
# 새로 추가
def validate_regex_patterns(patterns: List[str], case_sensitive: bool = False) -> List[str]:
    """
    Validate regex patterns and return list of invalid ones.
    Returns empty list if all patterns are valid.
    """
    invalid = []
    for p in patterns:
        try:
            re.compile(p if case_sensitive else p.casefold())
        except re.error:
            invalid.append(p)
    return invalid
```

#### scanner/scanner/search.py
```python
# 새로 추가
def _validate_regex_filters(filters: SearchFilters) -> List[str]:
    """Validate regex patterns in filters. Returns list of warnings."""
    warnings = []
    if not filters.regex:
        return warnings

    all_patterns = filters.wafer + filters.lot + filters.film
    invalid = validate_regex_patterns(all_patterns, filters.case_sensitive)
    for p in invalid:
        warnings.append(f"Invalid regex pattern: '{p}'")
    return warnings

# search_local, search_server에서 호출
notices: List[str] = _validate_regex_filters(filters)
```

---

### 2.6 로깅 표준화

#### scanner/scanner/cli.py
```python
# Before
from .utils import ensure_dir
def setup_logger(out_dir: str, verbose: bool = False) -> logging.Logger:
    ...  # 로컬 구현

# After
from scanner.common.logging import setup_logger
logger = setup_logger("scanner", args.out, verbose=args.verbose)
```

#### scanner/downloader/cli.py
```python
# Before
def setup_logger(out_dir: str, verbose: bool = False) -> logging.Logger:
    ...  # 중복된 로컬 구현

# After
from scanner.common.logging import setup_logger
logger = setup_logger("downloader", args.out, verbose=args.verbose)
```

---

## 3. 변경된 파일 목록

| 파일 | 변경 유형 |
|------|-----------|
| `scanner/common/__init__.py` | 신규 |
| `scanner/common/models.py` | 신규 |
| `scanner/common/config.py` | 신규 |
| `scanner/common/fs_local.py` | 신규 |
| `scanner/common/logging.py` | 신규 |
| `scanner/scanner/models.py` | 수정 (re-export) |
| `scanner/scanner/config.py` | 수정 (re-export) |
| `scanner/scanner/fs_local.py` | 수정 (re-export) |
| `scanner/scanner/film_index.py` | 수정 (디버그 제거) |
| `scanner/scanner/search.py` | 수정 (디버그 제거, regex 검증) |
| `scanner/scanner/ftp.py` | 수정 (디버그 제거, 중복 import) |
| `scanner/scanner/http_api.py` | 수정 (Factory 패턴) |
| `scanner/scanner/cli.py` | 수정 (공통 로깅) |
| `scanner/scanner/utils.py` | 수정 (regex 검증 함수) |
| `scanner/downloader/config.py` | 수정 (re-export) |
| `scanner/downloader/ftp_local.py` | 수정 (re-export) |
| `scanner/downloader/cli.py` | 수정 (공통 로깅) |

---

## 4. 프로젝트 구조 (After)

```
scanner-project/
└── scanner/
    ├── common/                  # [신규] 공유 모듈
    │   ├── __init__.py
    │   ├── models.py            # ServerConfig, SearchFilters, Hit
    │   ├── config.py            # read_server_list
    │   ├── fs_local.py          # LocalAdapter
    │   └── logging.py           # setup_logger
    ├── scanner/
    │   ├── cli.py               # [수정] 공통 로깅 사용
    │   ├── config.py            # [수정] re-export
    │   ├── models.py            # [수정] re-export
    │   ├── fs_local.py          # [수정] re-export
    │   ├── film_index.py        # [수정] 디버그 제거
    │   ├── scan_index.py
    │   ├── search.py            # [수정] 디버그 제거, regex 검증
    │   ├── ftp.py               # [수정] 디버그 제거
    │   ├── http_api.py          # [수정] Factory 패턴
    │   ├── utils.py             # [수정] regex 검증 함수
    │   └── policy.py
    ├── downloader/
    │   ├── cli.py               # [수정] 공통 로깅 사용
    │   ├── config.py            # [수정] re-export
    │   ├── ftp_local.py         # [수정] re-export
    │   ├── ftp_remote.py
    │   ├── planner.py
    │   ├── worker.py
    │   └── utils.py
    └── ui/
        └── src/
            └── App.tsx
```

---

## 5. 추가 권장사항 (미수행)

| 항목 | 설명 | 우선순위 |
|------|------|----------|
| 테스트 추가 | 리팩토링된 코드에 대한 단위 테스트 | 높음 |
| FTP deadline 개선 | 현재 스레드 기반 → signal/async 방식 | 중간 |
| 인덱스 캐싱 | JSON 파일 반복 로딩 문제 해결 | 중간 |
| resume 기능 구현 | downloader/worker.py의 미구현 기능 | 낮음 |
| 타입 힌트 강화 | 모든 함수에 타입 힌트 추가 | 낮음 |

---

## 6. 하위 호환성

- 모든 기존 import 경로가 유지됨 (re-export 방식)
- API 변경 없음
- 외부 의존성 변경 없음 (순수 stdlib 유지)
