import os
import aiohttp
import asyncio
import datetime
import websockets
import json
from aiohttp import web
from pydub import AudioSegment
from pydub.silence import detect_silence as pydub_detect_silence
from env_keys import get_openai_api_key

# Set up upload directory
UPLOAD_DIR = "uploaded_audio"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# Counter for unique naming
counter = 1

# Set up web server
app = web.Application()

# Replace this with your actual OpenAI API key
OPENAI_API_KEY = get_openai_api_key()

async def upload_audio(request):
    global counter

    reader = await request.multipart()
    field = await reader.next()

    # Generate a unique filename with timestamp and counter
    timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    unique_filename = f"audio_{timestamp}_{counter}.webm"
    save_path = os.path.join(UPLOAD_DIR, unique_filename)

    # Increment the counter for the next file
    counter += 1

    # Write the file to disk
    with open(save_path, 'wb') as f:
        while True:
            chunk = await field.read_chunk()  # 8192 bytes by default.
            if not chunk:
                break
            f.write(chunk)

    try:
        # Convert WebM to WAV and save it
        audio = AudioSegment.from_file(save_path, format="webm")
        wav_path = save_path.replace(".webm", ".wav")
        audio.export(wav_path, format="wav")
        print(f"Conversion from WebM to WAV successful. Saved as: {wav_path}")

        # Check for silence
        if detect_silence(wav_path):
            silent_wav_path = wav_path.replace(".wav", "_silence.wav")
            os.rename(wav_path, silent_wav_path)
            print(f"Silence detected. Renamed to: {silent_wav_path}")
            # Start conversation starter if it's the first time
            if counter == 2:  # If it's the first audio file after initial setup
                await start_conversation()
        else:
            print(f"No extended silence detected in: {wav_path}")

    except Exception as e:
        print(f"Error while processing audio file: {e}")
        return web.Response(text="Failed to process audio", status=500)

    return web.Response(text="Audio uploaded successfully", status=200)

def detect_silence(audio_path, silence_threshold=-40.0, min_silence_duration=4900):
    audio = AudioSegment.from_file(audio_path, format="wav")
    silence_ranges = pydub_detect_silence(audio, min_silence_len=min_silence_duration, silence_thresh=silence_threshold)
    return len(silence_ranges) > 0

async def start_conversation():
    try:
        async with websockets.connect("wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01",
                                      extra_headers={"Authorization": f"Bearer {OPENAI_API_KEY}",
                                                     "OpenAI-Beta": "realtime=v1"}) as ws:
            # Send initial session creation event
            event = {
                "type": "response.create",
                "response": {
                    "modalities": ["text"],
                    "instructions": "You are babyclare a human, ",
                }
            }
            await ws.send(json.dumps(event))
            
            # Wait for the session creation response
            async for message in ws:
                response_data = json.loads(message)
                print(f"Received message from OpenAI: {response_data}")

                # Check if the session is successfully created
                if response_data.get("type") == "session.created":
                    print(f"Conversation starter session created: {response_data}")

                    # After session is created, send a follow-up prompt to generate text response
                    follow_up_event = {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": "Can you provide a conversation starter?"
                                }
                            ]
                        }
                    }
                    await ws.send(json.dumps(follow_up_event))
                    print("Follow-up prompt sent to OpenAI.")

                # Look for the assistant's response
                elif response_data.get("type") == "conversation.item.created":
                    item = response_data.get("item", {})
                    if item.get("role") == "assistant":
                        # Log and save assistant's response
                        content = item.get("content", [])
                        if content and isinstance(content, list) and len(content) > 0:
                            assistant_response = content[0].get("text")
                            if assistant_response:
                                print(f"Assistant response received: {assistant_response}")

                                # Save the response to a text file
                                with open("conversation_responses.txt", "a") as response_file:
                                    response_file.write(f"{datetime.datetime.now()}: {assistant_response}\n")

                                break  # Break after receiving the assistant's response
                        else:
                            print("Warning: Assistant's response content is empty or not in expected format.")

    except Exception as e:
        print(f"Error while connecting to OpenAI: {e}")

app.router.add_post("/upload_audio", upload_audio)

if __name__ == "__main__":
    web.run_app(app, port=8000)
