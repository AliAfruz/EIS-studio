# Build EIS Gold Studio as a Windows EXE

## One-click method

1. Use a Windows 10 or Windows 11 computer.
2. Install 64-bit Python 3.11 or 3.12 from python.org. Keep the Python launcher enabled during installation.
3. Extract the EIS Gold Studio ZIP completely.
4. Double-click `build_windows_exe.bat`.
5. Choose:
   - `1` for a one-folder build (recommended first).
   - `2` for a single-file EXE.
6. Wait for the build to finish. The output folder opens automatically.

Recommended output:

```text
dist\EIS Gold Studio\EIS Gold Studio.exe
```

Single-file output:

```text
dist\EIS Gold Studio.exe
```

The destination computer does not need Python installed.

## Manual commands

Open Command Prompt in the project folder and run:

```bat
py -3 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install --upgrade pyinstaller
```

Recommended one-folder build:

```bat
python -m PyInstaller --noconfirm --clean --windowed --onedir --name "EIS Gold Studio" --icon "assets\eis_gold_studio.ico" --add-data "assets;assets" --hidden-import openpyxl --hidden-import PySide6.QtSvg main.py
```

Single-file build:

```bat
python -m PyInstaller --noconfirm --clean --windowed --onefile --name "EIS Gold Studio" --icon "assets\eis_gold_studio.ico" --add-data "assets;assets" --hidden-import openpyxl --hidden-import PySide6.QtSvg main.py
```

## Included custom icon

The package already includes your supplied artwork as:

- `assets/1.png` — application/window/taskbar image;
- `assets/eis_gold_studio.ico` — multi-resolution Windows EXE icon.

The one-click builder automatically embeds both files. No extra icon command is required.

## Debugging a build that does not open

Temporarily replace `--windowed` with `--console`, rebuild, and launch it from Command Prompt. The console will display the missing-module or startup error.

## Important

Build the Windows EXE on Windows. PyInstaller does not create a Windows executable from Linux or macOS.
