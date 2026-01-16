# Scanner Project Deployment Guide

이 문서는 다른 컴퓨터에서 Scanner 프로젝트를 설정하고 실행하는 방법을 안내합니다.

## 전제 조건 (Prerequisites)
1.  **Python 3.10 이상**: [python.org](https://www.python.org/)에서 설치.
    *   설치 시 "Add Python to PATH" 체크박스를 꼭 선택하세요.
2.  **Node.js 18 이상**: [nodejs.org](https://nodejs.org/)에서 설치 (UI 실행용).
    *   UI를 실행하지 않고 백엔드만 쓸거라면 필요 없습니다.
3.  **Git (선택 사항)**: 소스 코드를 옮길 때 유용하지만, USB나 압축 파일로 옮겨도 됩니다.

---

## 1. 소스 코드 복사
현재 프로젝트 폴더(`FTP_DN_PRJ_gemini`)를 새 컴퓨터의 원하는 위치(예: `D:\code\scanner`)로 복사하세요.
*   **주의:** `node_modules`, `out`, `__pycache__` 폴더는 용량이 크거나 불필요하므로 제외하고 복사하는 것이 좋습니다. (복사 후 새로 설치 권장)

## 2. Python 환경 설정 (백엔드)
터미널(PowerShell 또는 cmd)을 열고 프로젝트 폴더로 이동합니다.

```bash
cd D:\code\scanner
```

필요한 라이브러리를 설치합니다:
```bash
pip install -r requirements.txt
```

## 3. Node.js 환경 설정 (UI Front-End)
UI를 사용하려면 아래 명령어로 패키지를 설치합니다:
```bash
cd scanner/ui
npm install
```
(설치가 끝나면 다시 상위 폴더로 이동: `cd ..\..`)

## 4. 서버 설정 (servers.txt)
새 컴퓨터 환경에 맞게 `scanner/servers.txt` 파일을 수정해야 할 수 있습니다.
*   FTP 서버의 IP 주소 등을 확인하고 필요시 변경하세요.

## 5. 실행 방법

### 1) 백엔드 서버 실행 (항상 먼저 실행)
```bash
# 프로젝트 루트(D:\code\scanner)에서 실행
python -m scanner.cli --mode serve --server-file servers.txt --out out
```
*   `[HTTP] listening on http://127.0.0.1:8081` 메시지가 뜨면 성공입니다.

### 2) UI 실행 (새 터미널 창)
```bash
cd scanner/ui
npm run dev
```
*   브라우저가 열리며 `http://localhost:5173`으로 접속됩니다.

## 6. 문제 해결
*   **검색이 안 될 때:** 백엔드 서버가 실행 중인지 확인하세요.
*   **FTP 연결 실패:** `servers.txt`의 IP와 계정 정보를 확인하세요.
