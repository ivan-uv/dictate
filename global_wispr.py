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
HOTKEY = {keyboard.Key.ctrl, keyboard.Key.alt} # Using 'alt' for Option key
TRIGGER_KEY = keyboard.KeyCode.from_char('r')
FS = 16000
MODEL = "mlx-community/whisper-large-v3-turbo"

class WisprApp:
    def __init__(self):
        self.recording = False
        self.audio_frames = []
        self.current_keys = set()

    def paste_text(self, text):
        # 1. Copy to clipboard
        pyperclip.copy(text)
        # 2. Use AppleScript to simulate Command+V
        script = 'tell application "System Events" to keystroke "v" using command down'
        subprocess.run(['osascript', '-e', script])

    def toggle_record(self):
        if not self.recording:
            print("🔴 Recording started...")
            self.audio_frames = []
            self.recording = True
            self.stream = sd.InputStream(samplerate=FS, channels=1, callback=self.audio_callback)
            self.stream.start()
        else:
            print("✅ Recording stopped. Transcribing...")
            self.recording = False
            self.stream.stop()
            self.stream.close()
            self.process_audio()

    def audio_callback(self, indata, frames, time, status):
        if self.recording:
            self.audio_frames.append(indata.copy())

    def process_audio(self):
        audio_data = np.concatenate(self.audio_frames, axis=0)
        write("temp.wav", FS, audio_data)
        
        # Transcribe
        result = mlx_whisper.transcribe("temp.wav", path_or_hf_repo=MODEL)
        text = result['text'].strip()
        
        print(f"Result: {text}")
        self.paste_text(text)

    def on_press(self, key):
        if key in HOTKEY or key == TRIGGER_KEY:
            self.current_keys.add(key)
            if all(k in self.current_keys for k in HOTKEY) and TRIGGER_KEY in self.current_keys:
                self.toggle_record()

    def on_release(self, key):
        if key in self.current_keys:
            self.current_keys.remove(key)

app = WisprApp()

print(f"Wispr running in background. Press Ctrl + Option + R to toggle.")
with keyboard.Listener(on_press=app.on_press, on_release=app.on_release) as listener:
    listener.join()