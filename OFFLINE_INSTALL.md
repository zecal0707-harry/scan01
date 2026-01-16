# Offline Installation & Run Guide

This guide explains how to install and run the Scanner system on a PC without internet access.

## 1. Preparation (On Internet PC)

1.  **Build UI**:
    Ensure the frontend is built.
    ```powershell
    cd scanner/ui
    npm install
    npm run build
    cd ../..
    ```

2.  **Create Bundle**:
    Run the offline bundling script. This will download all Python dependencies and copy necessary files.
    ```powershell
    .\bundle_offline.ps1
    ```
    *   This creates a folder named `Scanner_Release_Package`.

## 2. Transfer

### Option A: USB (Recommended)
1.  Copy the entire `Scanner_Release_Package` folder to the target Offline PC.
2.  (Optional) Rename the folder to something simple like `C:\Scanner`.

### Option B: Email (Split Files)
If you cannot use USB/Cloud and have email size limits (e.g., 10MB):

1.  **Split**:
    *   On the internet PC, run `.\split_package.ps1`.
    *   This creates `scanner_pkg.zip.001`, `scanner_pkg.zip.002`... and `merge_package.bat`.

2.  **Send**:
    *   Email these files to yourself (one by one if needed).
    *   **Tip**: If extensions like `.001` are blocked, rename them to `.txt` before sending, and rename back after downloading.

3.  **Merge (On Offline PC)**:
    *   Put all files in one folder.
    *   Run `merge_package.bat`.
    *   This recreates `scanner_pkg.zip`.
    *   Right-click `scanner_pkg.zip` -> Extract All... to `C:\Scanner`.

## 3. Installation (On Offline PC)

1.  **Install Python**:
    *   Target PC must have Python 3.10+ installed.
    *   If not, download the installer from python.org on an internet PC and bring it over.
    *   **Important**: Check "Add Python to PATH" during installation.

2.  **Install Dependencies**:
    Open PowerShell or Command Prompt in the project folder and run:
    ```powershell
    pip install --no-index --find-links=packages -r requirements.txt
    ```
    *   This tells pip to look for libraries only in the `packages` folder we created.

## 4. Running the System

Since the UI is now served by the Python backend, you do **not** need Node.js.

1.  **Start Server**:
    ```powershell
    python -m scanner.cli --mode serve --server-file servers.txt --out out
    ```
    *   Run this in the project root folder.

2.  **Use UI**:
    *   Open Chrome or Edge.
    *   Go to `http://localhost:8081` (default port).
    *   Everything should work exactly like the online version.

## Troubleshooting

*   **"Component absent" errors**: Ensure you are running the command from the project root (where `Scanner_Release_Package` contents are).
*   **Port in use**: If 8081 is taken, add `--http-port 9090` to the python command.

## 5. Development / VS Code (Optional)

If you are using VS Code, you can run the server easily:

1.  **Open Project**: Open the `scanner-project` folder in VS Code.
2.  **Run**: Press **F5** or go to "Run and Debug" and click "Python: Run Scanner Server".
    *   This automatically sets up paths and arguments.
    *   The entry point file is `scanner/scanner/cli.py`, but you don't need to open it manually.
3.  **UI Build**:
    *   Press `Ctrl+Shift+P` -> type "Run Task" -> select `npm: build (UI)`.
