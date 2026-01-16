# Scanner/Downloader (local-first, FTP-capable)

FAB 데이터 검색 및 다운로드 시스템입니다. 로컬 파일시스템 또는 FTP 서버에서 Scan/Film 데이터를 검색하고 다운로드할 수 있습니다.

## 구성

- `scanner/` : 검색/인덱싱/HTTP API (`python -m scanner.cli ...`)
- `downloader/` : 다운로드 모듈 (UI 또는 CLI)
- `ui/` : React + Vite 기반 웹 UI
- `common/` : 공통 모듈 (config, logging, models)
- `MOCK_ROOT/` : 샘플 데이터 (Film List, auto scan data)

## 빠른 시작

### 1. 백엔드 서버 시작
```bash
python -m scanner.cli --mode serve --server-file servers.txt --out out --http-port 8081
```

### 2. UI 시작
```bash
cd ui
npm install  # 최초 1회
npm run dev
```

### 3. 접속
- UI: http://localhost:5173
- API: http://localhost:8081

## 검색 모드 vs 데이터 소스

### 검색 모드 (UI에서 선택)

검색 모드는 **어떻게 검색할지**를 결정합니다.

| 모드 | 설명 | 속도 |
|------|------|------|
| `자동 (both)` | cache 먼저 → 없으면 direct | 권장 |
| `cache` | 로컬에 저장된 인덱스 파일(*.json)에서 검색 | 빠름 (밀리초) |
| `direct` | 폴더를 직접 탐색하여 검색 | 느림 (초~분) |

### 데이터 소스 (servers.txt에서 설정)

데이터 소스는 **어디서 데이터를 가져올지**를 결정합니다. `direct` 모드에서만 영향을 미칩니다.

| 설정 | 설명 | 경로 예시 |
|------|------|-----------|
| `source=local` | 로컬 파일시스템 | `D:\Film List` |
| `source=network` | 네트워크 드라이브 (SMB/UNC) | `Z:\Film List` 또는 `\\192.168.1.100\share\Film List` |
| `source=ftp` (또는 생략) | FTP 서버에 연결 | `/Film List` |

**중요:** `cache` 모드는 항상 로컬 인덱스 파일에서 검색하므로 데이터 소스 설정과 무관합니다.

## 인덱스 관리

### CLI
```bash
# 전체 인덱싱 (Bootstrap)
python -m scanner.cli --mode bootstrap --server-file servers.txt --out out

# 증분 업데이트 (Update)
python -m scanner.cli --mode update --server-file servers.txt --out out
```

### UI
- Index Management 섹션에서 Bootstrap/Update 버튼 사용
- 상태 조회로 인덱스 현황 확인 가능

## 다운로드

### UI에서 직접 다운로드 (권장)
1. 검색 결과에서 항목 선택
2. Download to 경로 입력
3. Download Selected 버튼 클릭

### CLI로 다운로드
```bash
# JSON 내보내기 후 CLI 실행
python -m downloader.cli --server-file servers.txt --file exported.json --dest-root D:\DATA --overwrite resume
```

## servers.txt 예시

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

## API 엔드포인트

| 엔드포인트 | 설명 |
|------------|------|
| `GET /health` | 서버 상태 확인 |
| `GET /v1/servers` | 서버 목록 |
| `POST /v1/search/cache` | 캐시(인덱스) 검색 |
| `POST /v1/search/direct` | 서버 직접 탐색 |
| `POST /v1/download` | 선택 항목 다운로드 |
| `GET /v1/index/status` | 인덱스 상태 조회 |
| `POST /v1/index/bootstrap` | 전체 재인덱싱 |
| `POST /v1/index/update` | 증분 업데이트 |

## 문서

- `DATA_STRUCTURE.md` : 데이터 구조 및 명명 규칙
- `DEVELOPMENT_NOTES.md` : 개발 노트 및 트러블슈팅

## 참고

- 정책/튜닝 상수: `scanner/policy.py`
- 데이터 소스 전환: `source=local` 또는 `source=ftp` 메타 설정
- 경로 길이 제한: Windows 260자 이하 권장 (`dest_root`는 짧게)
