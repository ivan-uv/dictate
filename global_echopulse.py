import mlx_whisper
import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write
from pynput import keyboard
import pyperclip
import os
import subprocess
import time

# --- CONFIG ---
TRIGGER_KEY = keyboard.Key.cmd_r
FS = 16000
MODEL = "mlx-community/whisper-large-v3-turbo"

# Built-in macOS Sounds
SOUND_START = "/System/Library/Sounds/Funk.aiff"
SOUND_END = "/System/Library/Sounds/Blow.aiff"

class EchoPulse:
    def __init__(self):
        self.recording = False
        self.audio_frames = []
        self.is_held = False 
        os.makedirs("training_data", exist_ok=True)

    def play_sound(self, sound_path):
        # Plays sound in background so it doesn't lag the recording
        subprocess.Popen(["afplay", sound_path])

    def paste_text(self, text):
        pyperclip.copy(text)
        script = 'tell application "System Events" to keystroke "v" using command down'
        subprocess.run(['osascript', '-e', script])

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
        result = mlx_whisper.transcribe(audio_path, path_or_hf_repo=MODEL)
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

# --- RUN APP ---
app = EchoPulse()
print(f"🚀 EchoPulse is LIVE. Hold [Right Command] to speak.")

with keyboard.Listener(on_press=app.on_press, on_release=app.on_release) as listener:
    listener.join()