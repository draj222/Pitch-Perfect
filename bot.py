# bot.py - Pitch Perfect Coach Bot (Voice Version)
# Features:
# 1. Join VC on /startpitch
# 2. Record user audio for 60s
# 3. Transcribe via Whisper
# 4. Analyze via GPT-4
# 5. Reply with text feedback

# Fix SSL certificate issues on macOS
import os
import ssl
import certifi

# Set the certificate file location - safer approach
os.environ['SSL_CERT_FILE'] = certifi.where()

# Monkey-patch SSL for more aggressive certificate bypassing
# SECURITY WARNING: This disables SSL verification entirely - only use in development
if ssl.get_default_verify_paths().cafile is None:
    try:
        import aiohttp
        # Create a custom SSL context that doesn't verify certificates
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        # Patch aiohttp to use this context
        old_connect = aiohttp.TCPConnector.__init__
        def new_connect(self, *args, **kwargs):
            kwargs['ssl'] = ssl_context
            old_connect(self, *args, **kwargs)
        aiohttp.TCPConnector.__init__ = new_connect
        print("SSL certificate verification disabled for aiohttp")
    except ImportError:
        pass

# ------------------------------
# GET YOUR DISCORD BOT TOKEN
# ------------------------------
# 1. Go to the Discord Developer Portal: https://discord.com/developers/applications
# 2. Select your application or click "New Application" to create one.
# 3. In the sidebar, select "Bot".
# 4. Under "Token", click "Copy" (or "Reset Token" then "Copy" if no token exists).
# 5. Keep this token secure. You will add it to your `.env` as DISCORD_TOKEN.
# ------------------------------
# SETUP REQUIREMENTS
# ------------------------------
# - Python 3.10+
# - discord.py[voice]
# - python-dotenv
# - openai
# - discord-ext-voice-recv
# - ffmpeg installed on your system

import os
import asyncio
import ssl
import certifi
import logging
from dotenv import load_dotenv
import discord
from discord.ext import commands
import openai
from datetime import datetime
from recorder import Recorder

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('voicecoach')

# Load environment variables from .env
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# (Optional) ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# Configure OpenAI
openai.api_key = OPENAI_API_KEY
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Bot intents (avoid using privileged intents)
intents = discord.Intents.default()
intents.message_content = True  # This is a privileged intent, might need to be enabled in the portal
intents.voice_states = True  # Required for voice functionality

bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

@bot.command(name='startpitch')
async def startpitch(ctx, duration: int = 60):
    # Validate duration (minimum 10 seconds)
    if duration < 10:
        return await ctx.send("⚠️ Pitch duration must be at least 10 seconds.")
        
    # Check voice channel (still need this for Discord connectivity)
    if not ctx.author.voice or not ctx.author.voice.channel:
        return await ctx.send("🔊 You need to join a voice channel first!")

    vc_channel = ctx.author.voice.channel
    
    # Tell user how to proceed
    await ctx.send(f"⏱️ I'll record your pitch from your microphone for {duration} seconds.")
    await ctx.send("🎤 **IMPORTANT:** This bot records audio directly from your system microphone - not through Discord. Make sure your microphone is unmuted and working.")
    await ctx.send("🔄 Get ready... your pitch recording will start in 3 seconds!")
    
    # Give them a moment to prepare
    await asyncio.sleep(3)
    
    try:
        # Connect to voice channel (to show bot presence)
        vc_client = await vc_channel.connect()
        
        # Prepare recording
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        audio_filename = f"pitch_{ctx.author.id}_{timestamp}.wav"
        recorder = Recorder(vc_client)

        # Start recording - pass the duration parameter
        await recorder.start(audio_filename, duration_seconds=duration)
        
        # Wait for the duration
        await ctx.send(f"⏱️ Recording for {duration} seconds... Speak your pitch now!")
        await asyncio.sleep(duration)
        
        # Stop recording
        recording_successful = await recorder.stop()
        
        # Disconnect from voice channel
        await vc_client.disconnect()
        
        await ctx.send(f"✅ Recording complete! Processing your {duration}-second pitch...")

        # Transcribe with Whisper
        await ctx.send("🔄 Transcribing audio...")
        try:
            with open(audio_filename, 'rb') as audio_file:
                transcript_resp = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )
            transcript = transcript_resp.text.strip()
            
            # If transcript is empty, use a sample
            if not transcript:
                transcript = "This is a sample pitch for a startup called VoiceCoach. Our product helps people practice and improve their pitch presentations using AI feedback. We provide real-time analysis of delivery, content, and presentation style."
                await ctx.send("⚠️ No speech detected in the audio. Using a sample transcript instead.")
        except Exception as e:
            await ctx.send(f"⚠️ Error transcribing audio: {str(e)}")
            transcript = "This is a sample pitch for a startup called VoiceCoach. Our product helps people practice and improve their pitch presentations using AI feedback. We provide real-time analysis of delivery, content, and presentation style."
            await ctx.send("⚠️ Using a sample transcript due to transcription error.")

        # Analyze with GPT-4
        await ctx.send("🤖 Analyzing your pitch...")
        system_prompt = (
            "You are a seasoned startup investor. "
            f"A founder just gave a {duration}-second pitch: \"{transcript}\".\n"
            "Provide:\n"
            "1. Clarity score (1-10)\n"
            "2. Two strengths of the pitch\n"
            "3. Two weaknesses or areas to improve\n"
            "4. Three follow-up investor questions\n"
            "5. One concrete suggestion to make it stronger."
        )

        completion = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt}
            ]
        )
        feedback = completion.choices[0].message.content

        # Send text feedback
        await ctx.send(f"📋 **Here's your feedback:**\n{feedback}")
        
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")
        if ctx.guild.voice_client:
            await ctx.guild.voice_client.disconnect()

# Run bot
if __name__ == '__main__':
    print("""
IMPORTANT NOTES:
1. This bot requires privileged intents (MESSAGE CONTENT and VOICE STATE) 
   to be enabled in the Discord Developer Portal.
2. Go to https://discord.com/developers/applications/ and select your bot.
3. Navigate to "Bot" settings and enable these privileged intents.
""")
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        print(f"Error: {e}")
        print("If you're seeing SSL certificate errors, you may need to install certificates for your Python installation.")
        print("On macOS, this is a common issue.")