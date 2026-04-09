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
import json
from datetime import datetime

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
MODEL = os.environ.get("DICTATE_MODEL", "mlx-community/whisper-large-v3-turbo")

# Bias transcription toward technical / code-style speech (snake_case, APIs, etc.)
# Can be overridden at runtime via the DICTATE_INITIAL_PROMPT environment variable.
_BASE_PROMPT = os.environ.get(
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

# Custom vocabulary loaded from dictionary.txt (one word/phrase per line)
_DICTIONARY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dictionary.txt")
if os.path.exists(_DICTIONARY_PATH):
    with open(_DICTIONARY_PATH) as _f:
        _words = [w.strip() for w in _f if w.strip()]
    INITIAL_PROMPT = _BASE_PROMPT + " Custom vocabulary: " + ", ".join(_words) + "."
else:
    INITIAL_PROMPT = _BASE_PROMPT

# Built-in macOS Sounds
SOUND_START = "/System/Library/Sounds/Funk.aiff"
SOUND_END = "/System/Library/Sounds/Pop.aiff"
LOG_TRAINING = os.environ.get("DICTATE_LOG_TRAINING", "0").lower() in ("1", "true", "yes")
HISTORY_FILE = os.path.expanduser("~/Desktop/dictate.txt")
STATS_FILE = os.path.expanduser("~/Desktop/.dictate_stats.json")
HISTORY_MAX = 10

class Dictate:
    def __init__(self):
        self.recording = False
        self.audio_frames = []
        self.is_held = False
        if LOG_TRAINING:
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
        self.audio_frames = []
        self.recording = True
        self.stream = sd.InputStream(samplerate=FS, channels=1, callback=self.audio_callback)
        self.stream.start()
        self.play_sound(SOUND_START) # "Bloop"
        print("🔴 [HOLD] Recording...")

    def stop_recording(self):
        print("🟢 [RELEASED] Transcribing...")
        self.recording = False
        if hasattr(self, 'stream'):
            self.stream.stop()
            self.stream.close()
        self.process_audio()

    def process_audio(self):
        if not self.audio_frames: return

        audio_data = np.concatenate(self.audio_frames, axis=0)

        # Skip clips too short to contain speech (accidental taps)
        duration = len(audio_data) / FS
        if duration < 0.3:
            print("⏭️  Too short, skipping transcription.")
            self.play_sound(SOUND_END)
            return

        # Skip silence to avoid Whisper hallucinating CJK characters on empty audio
        rms = np.sqrt(np.mean(audio_data ** 2))
        if rms < 0.003:
            print("⏭️  Silence detected, skipping transcription.")
            self.play_sound(SOUND_END)
            return

        if LOG_TRAINING:
            timestamp = int(time.time())
            audio_path = f"training_data/sample_{timestamp}.wav"
            write(audio_path, FS, audio_data)
        else:
            import tempfile
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            audio_path = tmp.name
            tmp.close()
            write(audio_path, FS, audio_data)

        # Transcribe
        # condition_on_previous_text=False prevents runaway repetition loops on
        # longer clips — Whisper processes audio in 30s windows and normally feeds
        # its own output back as context, which reinforces hallucination loops.
        result = mlx_whisper.transcribe(
            audio_path,
            path_or_hf_repo=MODEL,
            initial_prompt=INITIAL_PROMPT,
            condition_on_previous_text=False,
        )
        text = result['text'].strip()

        if LOG_TRAINING:
            with open(f"training_data/sample_{timestamp}.txt", "w") as f:
                f.write(text)
        else:
            os.unlink(audio_path)

        self.play_sound(SOUND_END) # "Bleep"
        print(f"Result: {text}")
        self.paste_text(text)
        self._update_history(text, duration)

    def _update_history(self, text, duration):
        """Prepend transcript to ~/Desktop/dictate.txt, keeping the last 10."""
        import re
        timestamp = datetime.now().strftime("%b %-d %-I:%M%p").lower()
        new_entry = f"{text}\n\n--- {timestamp} ---"

        # Read existing transcript blocks
        old_raw = []
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                raw = f.read().strip()
            if raw:
                # Strip the stats block before parsing entries
                raw = re.split(r"\n\n╔═+╗", raw)[0].strip()
                if raw:
                    old_raw = re.findall(r"(.+?\n\n--- .+ ---)", raw, re.DOTALL)
        old_raw = old_raw[:HISTORY_MAX - 1]

        # Update stats
        stats = self._update_stats(text, duration)

        with open(HISTORY_FILE, "w") as f:
            f.write(new_entry)
            for block in old_raw:
                f.write("\n\n" + block.strip())
            f.write("\n\n" + self._render_stats(stats))

    def _update_stats(self, text, duration):
        """Update persistent stats and return the current totals."""
        now = datetime.now()
        month_key = now.strftime("%Y-%m")
        week_key = now.strftime("%Y-W%W")

        stats = {"lifetime": {}, "months": {}, "weeks": {}}
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, "r") as f:
                stats = json.load(f)

        chars = len(text)

        for bucket_name, key in [("lifetime", "all"), ("months", month_key), ("weeks", week_key)]:
            bucket = stats.setdefault(bucket_name, {})
            entry = bucket.setdefault(key, {"chars": 0, "seconds": 0.0, "count": 0})
            entry["chars"] += chars
            entry["seconds"] += duration
            entry["count"] += 1

        with open(STATS_FILE, "w") as f:
            json.dump(stats, f)

        return stats

    @staticmethod
    def _format_duration(seconds):
        """Format seconds into a human-readable string."""
        s = int(seconds)
        days, s = divmod(s, 86400)
        hours, s = divmod(s, 3600)
        minutes, s = divmod(s, 60)
        parts = []
        if days:
            parts.append(f"{days} Day{'s' if days != 1 else ''}")
        if hours:
            parts.append(f"{hours} Hour{'s' if hours != 1 else ''}")
        if minutes or not parts:
            parts.append(f"{minutes} Minute{'s' if minutes != 1 else ''}")
        return ", ".join(parts)

    def _render_stats(self, stats):
        """Render the stats block for the bottom of dictate.txt."""
        now = datetime.now()
        lt = stats.get("lifetime", {}).get("all", {})
        mo = stats.get("months", {}).get(now.strftime("%Y-%m"), {})
        wk = stats.get("weeks", {}).get(now.strftime("%Y-W%W"), {})

        lt_dur = self._format_duration(lt.get("seconds", 0))
        lt_chars = f"{lt.get('chars', 0):,}"
        lt_count = f"{lt.get('count', 0):,}"
        mo_chars = f"{mo.get('chars', 0):,}"
        mo_count = f"{mo.get('count', 0):,}"
        wk_chars = f"{wk.get('chars', 0):,}"
        wk_count = f"{wk.get('count', 0):,}"

        w = 48
        bar = "═" * (w - 2)
        return (
            f"╔{bar}╗\n"
            f"║{'d i c t a t e':^{w - 2}}║\n"
            f"╠{bar}╣\n"
            f"║{'':^{w - 2}}║\n"
            f"║{'Time spent talking to your computer:':^{w - 2}}║\n"
            f"║{lt_dur:^{w - 2}}║\n"
            f"║{'':^{w - 2}}║\n"
            f"╠{bar}╣\n"
            f"║  {'Lifetime':10} {lt_count:>8} clips  {lt_chars:>10} chars  ║\n"
            f"║  {'This Month':10} {mo_count:>8} clips  {mo_chars:>10} chars  ║\n"
            f"║  {'This Week':10} {wk_count:>8} clips  {wk_chars:>10} chars  ║\n"
            f"╠{bar}╣\n"
            f"║{'local · private · fast':^{w - 2}}║\n"
            f"╚{bar}╝\n"
        )

    def on_press(self, key):
        if key == TRIGGER_KEY and not self.is_held:
            self.is_held = True
            self.start_recording()

    def on_release(self, key):
        if key == TRIGGER_KEY:
            self.is_held = False
            if self.recording:
                self.stop_recording()

def run():
    """Run Dictate (blocking). Single entry point for the app."""
    app = Dictate()
    print("🚀 Dictate is LIVE. Hold [Right Command] to speak.")
    with keyboard.Listener(on_press=app.on_press, on_release=app.on_release) as listener:
        listener.join()


if __name__ == "__main__":
    run()