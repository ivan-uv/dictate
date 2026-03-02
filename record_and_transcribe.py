import mlx_whisper
import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write
import os

def record_audio(filename="input.wav", fs=16000):
    print("\n[STEP 1] Press ENTER to start recording...")
    input()
    
    print("Recording... (Press ENTER to stop)")
    recording = []
    
    # Define a callback to store audio data
    def callback(indata, frames, time, status):
        recording.append(indata.copy())

    with sd.InputStream(samplerate=fs, channels=1, callback=callback):
        input() # Wait for second Enter press
        
    print("Recording stopped.")
    audio_data = np.concatenate(recording, axis=0)
    write(filename, fs, audio_data)
    return filename

def run_pipeline():
    audio_file = record_audio()
    
    print(f"\n[STEP 2] Transcribing with MLX-Whisper...")
    # Using 'turbo' for near-instant feedback on your M3 Max
    result = mlx_whisper.transcribe(audio_file, path_or_hf_repo="mlx-community/whisper-large-v3-turbo")
    
    print("\n--- YOUR WORDS ---")
    print(result['text'].strip())
    print("------------------\n")

if __name__ == "__main__":
    while True:
        run_pipeline()
        print("Ready for next one? (Ctrl+C to quit)")