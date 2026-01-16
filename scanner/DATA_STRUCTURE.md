# Scanner Project - Data Structure Documentation

이 문서는 Scanner Project의 데이터 구조, 명명 규칙, 검색 로직에 대해 설명합니다.

---

## 1. 개요

Scanner Project는 두 가지 주요 데이터 소스를 다룹니다:

| 서버 역할 | 설명 | 루트 폴더 |
|-----------|------|-----------|
| **Film** | Film Recipe 파일 저장소 | `Film List/` |
| **Scan** | Wafer 스캔 데이터 저장소 | `auto scan data/` |

---

## 2. Film List 구조 (Film Server)

### 2.1 폴더 구조

```
Film List/
├── as0001/
│   └── strategy.ini
├── as0002/
│   └── strategy.ini
├── as0003/
│   └── strategy.ini
└── ...
```

### 2.2 구성 요소

| 요소 | 설명 | 예시 |
|------|------|------|
| **Film Folder** | Recipe 파일이 저장된 폴더 (prefix + 숫자) | `as0001`, `as0002` |
| **strategy.ini** | Film Recipe 정보가 담긴 설정 파일 | - |
| **StrategyName** | Film Recipe의 실제 이름 | `WQKJ_ETCH_METALDEP1_240515` |

### 2.3 strategy.ini 파일 형식

```ini
[Strategy]
StrategyName = WQKJ_ETCH_METALDEP1_240515
Created = 2025-12-23 12:01:27.565830
```

### 2.4 Film Recipe Name 규칙

```
[제품코드]_[공정타입]_[공정상세]_[날짜YYMMDD]
```

예시:
- `WQKJ_ETCH_METALDEP1_240515` → 제품 WQKJ, ETCH 공정, METALDEP1, 24년 5월 15일
- `GE_PHOTO_VIA_HOLE_240704` → 제품 GE, PHOTO 공정, VIA_HOLE, 24년 7월 4일

---

## 3. Auto Scan Data 구조 (Scan Server)

### 3.1 폴더 구조

```
auto scan data/
└── [Class]/
    └── [Wafer]/
        └── [Lot]/
            └── [Film]/
                └── [Date]/
                    └── Result.csv
```

### 3.2 실제 예시

```
auto scan data/
└── CLN/                                    ← Class (공정 분류)
    └── AHNL_CLN_METALDEP1_TEST/           ← Wafer (Wafer Recipe Name)
        └── AHNL4204/                       ← Lot (Lot ID)
            └── FBBU_CLN_GAP_FILL_241224/  ← Film (Film Recipe Name)
                └── 20241025/               ← Date (스캔 날짜)
                    └── Result.csv
```

### 3.3 구성 요소 상세

| 레벨 | 요소 | 설명 | 명명 규칙 |
|------|------|------|-----------|
| 1 | **Class** | 공정 분류 | `CLN`, `CMP`, `ETCH`, `MI`, `PHOTO`, `THIN_FILM` |
| 2 | **Wafer** | Wafer Recipe Name | `[제품코드]_[공정명]_[접미어]` |
| 3 | **Lot** | Lot ID | `[제품코드4][숫자4]` 또는 `[제품코드4][숫자4][영문2]` |
| 4 | **Film** | Film Recipe Name | strategy.ini의 StrategyName과 동일 |
| 5 | **Date** | 스캔 날짜 | `YYYYMMDD` (8자리 숫자) |

### 3.4 Wafer Recipe Name 규칙

```
[제품코드]_[공정타입]_[공정상세]_[접미어]
```

접미어 종류:
- `CM01`, `CM02` - Change Model
- `RUN1` - Run
- `RE01` - Retry
- `TEST` - Test

예시:
- `AHNL_CLN_METALDEP1_TEST`
- `WQ6D_ETCH_POLY_GATE_CM02`
- `IGYH_PHOTO_VIA_HOLE_CM01`

### 3.5 Lot ID 규칙

```
[제품코드 4자리][숫자 4자리][옵션: 영문 2자리]
```

예시:
- `AHNL4204` - 기본 Lot
- `VR6J1237NG` - Split Lot (영문 2자리 추가)

---

## 4. 인덱스 파일 구조

### 4.1 Film Index (recipes)

파일 위치: `out/recipes/{server}_recipes_index.json`

```json
{
  "server": "S_FILM_1",
  "recipes_root": "D:\\...\\Film List",
  "generated_at": null,
  "updated_at": null,
  "folders": {
    "as0001": {
      "path": "D:\\...\\Film List/as0001",
      "strategy": "WQKJ_ETCH_METALDEP1_240515"
    }
  },
  "by_recipe": {
    "WQKJ_ETCH_METALDEP1_240515": [
      "D:\\...\\Film List/as0001"
    ]
  },
  "stats": {
    "folders": 500,
    "recipes": 500
  }
}
```

### 4.2 Scan Lots Index

파일 위치: `out/required/{server}_lots_index.json`

```json
{
  "server": "S_SCAN_1",
  "lots_index": {
    "AHNL4204": [
      "D:\\...\\auto scan data/CLN/AHNL_CLN_METALDEP1_TEST/AHNL4204"
    ]
  }
}
```

### 4.3 Scan Films Index

파일 위치: `out/required/{server}_films_index.json`

```json
{
  "server": "S_SCAN_1",
  "mode": "map",
  "films_index": {
    "D:\\...\\CLN/AHNL_CLN_METALDEP1_TEST/AHNL4204": [
      "D:\\...\\AHNL4204/FBBU_CLN_GAP_FILL_241224/20241025"
    ]
  }
}
```

---

## 5. 검색 로직

### 5.1 경로에서 요소 추출

```python
# 경로 예시
path = ".../class/wafer/lot/film/date"

# Wafer 추출: lot의 부모 디렉토리
wafer_name = basename(dirname(lot_path))

# Film 추출: date의 부모 디렉토리 (또는 마지막 요소)
def extract_film_from_scan_path(p):
    parts = p.split("/")
    last = parts[-1]
    if re.match(r"^\d{8}$", last):  # 8자리 날짜면
        return parts[-2]             # film 반환
    return last
```

### 5.2 Film Recipe 링크

Scan 데이터의 Film 폴더명과 Film List의 StrategyName을 매칭:

```
Scan: .../lot/WQKJ_ETCH_METALDEP1_240515/20241025
                ↓ 매칭
Film List: as0001/strategy.ini → StrategyName = WQKJ_ETCH_METALDEP1_240515
```

### 5.3 검색 필터

| 필터 | 설명 | 예시 |
|------|------|------|
| `wafer` | Wafer Recipe Name 검색 | `AHNL_CLN`, `WQ6D_ETCH` |
| `lot` | Lot ID 검색 | `AHNL4204`, `WQ6D7681` |
| `film` | Film Recipe Name 검색 | `WQKJ_ETCH`, `FBBU_CLN` |
| `exact` | 정확히 일치 | `true/false` |
| `regex` | 정규식 사용 | `true/false` |
| `link_recipe` | Film Recipe 링크 포함 | `true/false` |

---

## 6. 서버 설정 (servers.txt)

### 6.1 형식

```
# name, ip, max_depth, save_level, user, pass, meta...
# source=local: 로컬 파일시스템, source=network: 네트워크 드라이브, source=ftp: FTP 서버

# 로컬 파일시스템
S_FILM_LOCAL,127.0.0.1,3,2,USER,PASS,role=film,group=G1,root=D:\Film List,prefix=as,source=local

# 네트워크 드라이브 (드라이브 문자 또는 UNC 경로)
S_FILM_NET,192.168.1.100,3,2,USER,PASS,role=film,group=G1,root=Z:\Film List,prefix=as,source=network
S_SCAN_NET,192.168.1.100,3,2,USER,PASS,role=scan,group=G1,root=\\192.168.1.100\share\auto scan data,source=network

# FTP 서버
S_FILM_FTP,192.168.1.100,3,2,ftpuser,ftppass,role=film,group=G1,root=/Film List,prefix=as,source=ftp
```

### 6.2 메타데이터 설명

| 키 | 설명 | 예시 |
|----|------|------|
| `role` | 서버 역할 | `film`, `scan` |
| `group` | 서버 그룹 | `G1` |
| `root` | 루트 경로 | `D:\data`, `Z:\share`, `\\server\path`, `/ftp/path` |
| `prefix` | Film 폴더 접두사 | `as` |
| `source` | 데이터 소스 | `local`, `network`, `ftp` |
| `pool_size` | FTP 연결 풀 크기 | `4` |

### 6.3 검색 모드 vs 데이터 소스

**검색 모드 (UI에서 선택):**
- `cache`: 로컬에 저장된 인덱스 파일(*.json)에서 검색 (빠름)
- `direct`: 폴더를 직접 탐색하여 검색 (느림, 최신 데이터)

**데이터 소스 (servers.txt에서 설정):**
- `source=local`: 로컬 파일시스템 (예: `D:\Film List`)
- `source=network`: 네트워크 드라이브/SMB/UNC (예: `Z:\Film List`, `\\server\share`)
- `source=ftp` (또는 생략): FTP 서버에 연결

**중요:** `cache` 모드는 항상 로컬 인덱스 파일에서 검색하므로 `source` 설정과 무관합니다. `source` 설정은 `direct` 모드에서만 영향을 미칩니다.

---

## 7. API 엔드포인트

### 7.1 Health Check

```
GET /health
Response: {"ok": true, "time": "2026-01-10T12:00:00+09:00"}
```

### 7.2 서버 목록

```
GET /v1/servers
Response: {"servers": [...], "count": 2}
```

### 7.3 캐시 검색 (Cache)

```
POST /v1/search/cache
Content-Type: application/json

{
  "roles": ["scan"],
  "wafer": ["AHNL"],
  "lot": ["AHNL4204"],
  "film": ["WQKJ"],
  "link_recipe": true
}
```

### 7.4 직접 탐색 (Direct)

```
POST /v1/search/direct
Content-Type: application/json

{
  "roles": ["scan"],
  "lot": ["AHNL4204"],
  "link_recipe": true
}
```

### 7.5 다운로드

```
POST /v1/download
Content-Type: application/json

{
  "hits": [...],
  "dest_root": "D:\\DATA",
  "overwrite": "resume",
  "dest_mode": "simple"
}
```

### 7.6 인덱스 관리

```
GET /v1/index/status          # 인덱스 상태 조회
POST /v1/index/bootstrap      # 전체 재인덱싱
POST /v1/index/update         # 증분 업데이트
```

---

## 8. 테스트 데이터 예시

### 8.1 검증된 테스트 데이터

| 필드 | 값 | 설명 |
|------|-----|------|
| Wafer | `AHNL_CLN_METALDEP1_TEST` | Wafer Recipe Name |
| Wafer | `WQ6D_ETCH_POLY_GATE_CM02` | Wafer Recipe Name |
| Lot | `AHNL4204` | Lot ID |
| Lot | `WQ6D7681` | Lot ID |
| Film | `WQKJ_ETCH_METALDEP1_240515` | Film Recipe Name |
| Film | `GE_PHOTO_VIA_HOLE_240704` | Film Recipe Name |

### 8.2 테스트 방법

1. **Wafer 검색**: Role=scan, Wafer=`AHNL_CLN`
2. **Lot 검색**: Role=scan, Lot=`AHNL4204`
3. **Film 검색 + 링크**: Role=scan, Film=`WQKJ_ETCH`, Link Recipe=true

---

## 9. 코드 파일 참조

| 파일 | 설명 |
|------|------|
| `scanner/cli.py` | CLI 진입점 |
| `scanner/scan_index.py` | Scan 데이터 인덱싱 |
| `scanner/film_index.py` | Film 데이터 인덱싱 |
| `scanner/search.py` | 검색 로직 |
| `scanner/http_api.py` | HTTP API 서버 |
| `scanner/utils.py` | 유틸리티 함수 |
| `scanner/policy.py` | 정책 상수 및 헬퍼 |

---

## 10. 변경 이력

| 날짜 | 변경 내용 |
|------|-----------|
| 2026-01-14 | `source=network` 옵션 추가 (네트워크 드라이브/SMB/UNC 지원) |
| 2026-01-14 | 변수명 명확화: `local=1` → `source=local`, `is_local` → `use_local_fs`, 검색 모드 vs 데이터 소스 구분 문서화 |
| 2026-01-11 | API 엔드포인트 이름 변경 (local→cache, server→direct), 다운로드/인덱스 관리 API 추가 |
| 2026-01-10 | 초기 문서 작성, 데이터 구조 규칙 정리 |
