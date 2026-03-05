import mlx_whisper
import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write
from pynput import keyboard
import pyperclip
import os
import subprocess
import threading
import time

# macOS pasteboard save/restore (preserves clipboard across transcript paste)
def _pasteboard_snapshot():
    """Capture current clipboard contents (all types). Returns None on non-macOS or failure."""
    try:
        from AppKit import NSPasteboard
        pb = NSPasteboard.generalPasteboard()
        types = pb.types()
        if not types:
            return None
        snapshot = {}
        for t in types:
            data = pb.dataForType_(t)
            if data is not None:
                snapshot[t] = data
        return snapshot if snapshot else None
    except Exception:
        return None


def _pasteboard_restore(snapshot):
    """Restore clipboard from a snapshot. No-op if snapshot is None or empty."""
    if not snapshot:
        return
    try:
        from AppKit import NSPasteboard
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        types = list(snapshot.keys())
        pb.declareTypes_owner_(types, None)
        for t, data in snapshot.items():
            pb.setData_forType_(data, t)
    except Exception:
        pass

# --- CONFIG ---
TRIGGER_KEY = keyboard.Key.cmd_r
FS = 16000
MODEL = "mlx-community/whisper-large-v3-turbo"

# Bias transcription toward technical / code-style speech (snake_case, APIs, etc.)
# Can be overridden at runtime via the DICTATE_INITIAL_PROMPT environment variable.
INITIAL_PROMPT = os.environ.get(
    "DICTATE_INITIAL_PROMPT",
    (
        "Transcribing mostly technical dictation for programming, code, and terminal commands. "
        "Prefer snake_case for identifiers when appropriate, for example: function_name, "
        "api_client, http_request, gpu_memory, numpy_array, config_dict, cli_tool. "
        "Keep acronyms like HTTP, API, GPU, CLI uppercase. "
        "When the speaker enumerates several issues or items (e.g. 'there are three things ... the UI, the lag, and the foo bar'), "
        "format the output as a short introduction line followed by a markdown-style list with each item on its own line starting with '- '."
    ),
)

# Built-in macOS Sounds
SOUND_START = "/System/Library/Sounds/Funk.aiff"
SOUND_END = "/System/Library/Sounds/Pop.aiff"

class Dictate:
    def __init__(self):
        self.recording = False
        self.audio_frames = []
        self.is_held = False 
        os.makedirs("training_data", exist_ok=True)

    def play_sound(self, sound_path):
        # Plays sound in background so it doesn't lag the recording
        subprocess.Popen(["afplay", sound_path])

    def paste_text(self, text):
        snapshot = _pasteboard_snapshot()
        pyperclip.copy(text)
        script = 'tell application "System Events" to keystroke "v" using command down'
        subprocess.run(['osascript', '-e', script])
        # Restore previous clipboard after paste so next Cmd+V pastes what user had copied
        threading.Timer(0.35, lambda: _pasteboard_restore(snapshot)).start()

    def audio_callback(self, indata, frames, time, status):
        if self.recording:
            self.audio_frames.append(indata.copy())

    def start_recording(self):
        self.play_sound(SOUND_START) # "Bloop"
        print("🔴 [HOLD] Recording...")
        self.audio_frames = []
        self.recording = True
        self.stream = sd.InputStream(samplerate=FS, channels=1, callback=self.audio_callback)
        self.stream.start()

    def stop_recording(self):
        print("✅ [RELEASED] Transcribing...")
        self.recording = False
        if hasattr(self, 'stream'):
            self.stream.stop()
            self.stream.close()
        self.process_audio()

    def process_audio(self):
        if not self.audio_frames: return
        
        timestamp = int(time.time())
        audio_path = f"training_data/sample_{timestamp}.wav"
        
        audio_data = np.concatenate(self.audio_frames, axis=0)
        write(audio_path, FS, audio_data)
        
        # Transcribe
        result = mlx_whisper.transcribe(
            audio_path,
            path_or_hf_repo=MODEL,
            initial_prompt=INITIAL_PROMPT,
        )
        text = result['text'].strip()
        
        with open(f"training_data/sample_{timestamp}.txt", "w") as f:
            f.write(text)

        self.play_sound(SOUND_END) # "Bleep"
        print(f"Result: {text}")
        self.paste_text(text)

    def on_press(self, key):
        if key == TRIGGER_KEY and not self.is_held:
            self.is_held = True
            self.start_recording()

    def on_release(self, key):
        if key == TRIGGER_KEY:
            self.is_held = False
            self.stop_recording()

def run():
    """Run Dictate (blocking). Single entry point for the app."""
    app = Dictate()
    print("🚀 Dictate is LIVE. Hold [Right Command] to speak.")
    with keyboard.Listener(on_press=app.on_press, on_release=app.on_release) as listener:
        listener.join()


if __name__ == "__main__":
    run()