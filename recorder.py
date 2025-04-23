import discord
import wave
import pyaudio
import asyncio
import threading
import struct
import os
import time
import tempfile
import queue

class Recorder:
    def __init__(self, voice_client):
        self.voice_client = voice_client  # Keep this for Discord API compatibility
        self.is_recording = False
        self.filename = None
        self.audio_thread = None
        self.audio_queue = queue.Queue()
        
        # PyAudio settings
        self.chunk = 1024
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 16000  # 16kHz - good for speech recognition
        self.p = pyaudio.PyAudio()
        
    def _record_thread(self, duration_seconds):
        """Thread function to record audio from microphone"""
        try:
            # Open microphone stream
            stream = self.p.open(format=self.format,
                                channels=self.channels,
                                rate=self.rate,
                                input=True,
                                frames_per_buffer=self.chunk)
            
            print(f"Recording started for {duration_seconds} seconds")
            frames = []
            
            # Calculate how many chunks we need for the duration
            total_chunks = int(self.rate / self.chunk * duration_seconds)
            
            # Record data in chunks
            for i in range(0, total_chunks):
                if not self.is_recording:
                    break
                data = stream.read(self.chunk)
                frames.append(data)
            
            # Stop and close the stream
            stream.stop_stream()
            stream.close()
            
            # Put the frames in the queue
            self.audio_queue.put(frames)
            print("Recording complete")
            
        except Exception as e:
            print(f"Error in recording thread: {e}")
            self.audio_queue.put(None)  # Signal error
            
    async def start(self, filename, duration_seconds=60):
        """Start recording audio from the microphone"""
        self.filename = filename
        self.is_recording = True
        
        # Create parent directory if needed
        os.makedirs(os.path.dirname(os.path.abspath(self.filename)), exist_ok=True)
        
        # Start recording in a separate thread
        self.audio_thread = threading.Thread(
            target=self._record_thread,
            args=(duration_seconds,)
        )
        self.audio_thread.daemon = True
        self.audio_thread.start()
        
        print(f"Started recording to {self.filename}")
        return True
        
    async def stop(self):
        """Stop recording and save the audio file"""
        if not self.is_recording:
            return False
            
        print("Stopping recording...")
        self.is_recording = False
        
        # Wait for the recording thread to finish
        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=5.0)  # Wait up to 5 seconds
            
        # Get the recorded frames from the queue
        try:
            frames = self.audio_queue.get(timeout=5.0)
            if frames is None:
                print("No audio data received")
                return await self._create_fallback()
                
            # Write WAV file
            try:
                with wave.open(self.filename, 'wb') as wf:
                    wf.setnchannels(self.channels)
                    wf.setsampwidth(self.p.get_sample_size(self.format))
                    wf.setframerate(self.rate)
                    wf.writeframes(b''.join(frames))
                    
                print(f"Saved audio to {self.filename} ({len(frames)} frames)")
                return True
            except Exception as e:
                print(f"Error saving audio file: {e}")
                return await self._create_fallback()
        except queue.Empty:
            print("Timed out waiting for audio data")
            return await self._create_fallback()
            
    async def _create_fallback(self):
        """Create a fallback audio file"""
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(os.path.abspath(self.filename)), exist_ok=True)
            
            sample_file = "sample_pitch.wav"
            if os.path.exists(sample_file):
                with open(sample_file, 'rb') as src, open(self.filename, 'wb') as dst:
                    dst.write(src.read())
                print(f"Used sample audio file as fallback for {self.filename}")
            else:
                # Create a test WAV file with a 440Hz tone (speech-like frequency)
                with wave.open(self.filename, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    
                    # Create 5 seconds of 440Hz tone
                    duration = 5.0  # seconds
                    frequency = 440.0  # A4 note
                    num_samples = int(duration * 16000)
                    
                    # Generate sine wave
                    for i in range(num_samples):
                        sample = int(32767.0 * 0.5 * (i % int(16000/frequency)) / (16000/frequency))
                        wf.writeframes(struct.pack('<h', sample))
                
                print(f"Created test tone file: {self.filename}")
                
            # Verify the file exists
            if os.path.exists(self.filename):
                print(f"Confirmed file exists at {self.filename}")
                return False
            else:
                print(f"WARNING: Failed to create file at {self.filename}")
                return False
                
        except Exception as e:
            print(f"Error creating fallback file: {e}")
            return False
            
    def __del__(self):
        """Clean up PyAudio resources"""
        if hasattr(self, 'p'):
            self.p.terminate()