# Auto Clicker (personal use)

Ad-free, lightweight Windows auto clicker. Python + CustomTkinter + pyautogui + pynput.

## Run
1. Install Python 3.10+ (tick "Add Python to PATH").
2. Double-click `run.bat` (creates a virtual env, installs dependencies, starts the app).

## Build the .exe
Double-click `build_exe.bat` -> `dist\AutoClicker.exe` (the script also embeds the logo and the icon).
- If an antivirus flags the single-file build, change `--onefile` to `--onedir` in the script
  (folder build is flagged less often) or add the folder to Windows Defender exclusions.
- Profiles and recent files are stored in `%APPDATA%\AutoClicker`, not next to the exe.

## Usage
| Key | Action |
|-----|--------|
| F8  | Start / Stop (works while another program has focus) |
| F9  | Record the cursor position as a new point (Multi Click mode) |

- **Single Click**: left-clicks at the current cursor position every *Interval* ms.
  Pressing the on-screen Start button waits 3 s so you can move the cursor to the target.
  (F8 starts immediately.)
- **Multi Click**: opens the Click Queue window. Each point has its own *Delay after (ms)*:
  the wait after clicking that point (for the last point: the wait before the next cycle).
- **Cycle limit**: one cycle = one pass through all points (Single mode: one click). 0/blank = unlimited.
- **Human Mode**: cursor offset of up to +-3 px (Multi mode) and delay variation of
  +-15 % (at least +-2 ms). It reduces simple pattern detection only; it cannot hide the
  fact that clicks are synthetic, so anti-cheat systems may still detect them.
- **Preview Route**: moves the cursor slowly through every point without clicking.
- **Timer Auto-Start**: arms a start at HH:MM (24 h clock). The app must stay open and the PC awake.
  If the PC wakes up more than 2 minutes after the target, the timer moves to the next day.
- **Profiles (.acp)**: Export/Import the Multi Click queue + settings. Up to 5 recent files in the dropdown.

## Language, About and credits
- **Language**: dropdown at the top-left (English, Bahasa Indonesia, Espanol, Francais, Deutsch,
  Portugues, Italiano, Russian, Turkce, Tieng Viet, Thai, Japanese, Korean, Simplified Chinese).
  The choice is remembered in `%APPDATA%\AutoClicker\config.json`. Default: English.
- **About**: click the app logo at the top-right (GitHub, Instagram, X and Saweria links).
- Logo files live in `assets\` (`logo.png` for the UI, `icon.ico` for the exe/window icon).
  Add a language by creating a new dict in a `locales_*.py` file and listing it in `i18n.py`;
  any missing text falls back to English.

## Safety
- **Kill-switch**: moving the cursor into the top-left corner of the main screen force-closes the app.
  In Multi mode the app stops teleporting the cursor while you are moving the mouse, so you can
  always reach the corner. Points closer than 12 px to that corner cannot be recorded.
- **Input validation**: numeric fields only accept digits; delays must be 1 ms - 1 h.
- **.acp validation**: extension, size, JSON structure, value ranges and a checksum are checked;
  invalid files are rejected with a message and nothing is loaded.

## Notes
- Some games/anti-cheat systems forbid auto clickers in their terms of service. Use at your own risk.
- Programs running as Administrator ignore simulated input from a normal-privilege app;
  run the clicker as Administrator too if you need to click inside them.
