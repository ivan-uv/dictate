# Dictate (Local STT)

**Objective:** High-speed, private, local speech-to-text with "Hold-to-Record" global hotkey functionality, optimized for Apple Silicon.

---

## ❓ Why I Built This
I wanted a seamless, privacy-first way to dictate text directly into any macOS application without relying on cloud-based services. This project was built to:
1.  **Explore Apple Silicon Performance:** Leveraging the Neural Engine via `mlx-whisper` for near-instant inference.
2.  **Master Platform-Native Integration:** Implementing global hotkeys (`pynput`) and high-fidelity clipboard management (using macOS `NSPasteboard` to preserve user data during pastes).
3.  **Create a Data Flywheel:** Automatically logging audio and transcripts to `training_data/` for future fine-tuning and model improvement.

---

## 🏗 Current Architecture
-   **Engine:** `mlx-whisper` (optimized for Apple Silicon).
-   **Model:** `whisper-large-v3-turbo` (loaded into Unified Memory).
-   **Audio Capture:** `sounddevice` + `scipy` (16kHz Mono).
-   **Global Control:** `pynput` listening for `Right Command` (`cmd_r`).
-   **Integration:** Automated GUI pasting using AppleScript (`osascript`) with a snapshot/restore mechanism to preserve the previous clipboard state.
-   **Data Logging:** Automatic storage of `.wav` and `.txt` pairs in `/training_data` for future fine-tuning.

---

## 🚀 Execution
Single entry point (run via `uv` for dependencies):

```bash
uv run main.py
```

Or after installing the project: `dictate` (see `pyproject.toml` scripts).

---

## 🛠 Features Implemented
1.  **Hold-to-Record:** Logic implemented via `on_press` and `on_release` with a boolean gate to prevent trigger-spamming.
2.  **Audio UI (Earcons):** Uses macOS system sounds (`Funk.aiff`, `Pop.aiff`) to provide non-visual feedback for recording states.
3.  **Clipboard Preservation:** Uses `pyobjc` to snapshot the clipboard before pasting the transcript and restores it 350ms later, ensuring your workflow isn't interrupted.
4.  **Local Privacy:** 0% cloud dependency; data never leaves your machine.

---

## 📈 Roadmap & Future-Proofing

### 1. Smart Formatting
Bias the model toward technical speech (e.g., snake_case) using Whisper's `initial_prompt` or a local LLM refiner (via Ollama).

### 2. Fine-Tuning
Utilize the collected `training_data/` to train a lightweight adapter using **MLX-LoRA** for jargon-specific accuracy.

### 3. Background Persistence (Launch Agent)
To move away from an open terminal, a `com.dictate.plist` can be added to `~/Library/LaunchAgents`. This allows the script to run as a background daemon that starts at login.

**Draft `plist` logic:**
- Label: `com.dictate.app`
- ProgramArguments: `[path/to/uv, run, path/to/main.py]`
- RunAtLoad: `true`

### 4. Menu Bar UI (The "Product" Layer)
Wrapping the core logic in **Rumps** (a Python library for macOS menu bar apps) would provide a visual "Recording..." indicator in the system tray and a toggle for "Sleep Mode," moving the project from a CLI tool to a native-feeling utility.

---

## 📝 Developer Notes
-   **Memory Management:** Designed for M3 Max; handles `large-v3` easily.
-   **Permissions:** Ensure **Accessibility** permissions are granted for your terminal or `/usr/bin/osascript` in System Settings.
-   **Dependencies:** Managed via `uv`. Key libraries: `mlx-whisper`, `sounddevice`, `pynput`, `pyperclip`, `pyobjc-framework-Cocoa`.
