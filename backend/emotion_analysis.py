import os
import asyncio
import json
import logging
from hume import HumeStreamClient
from hume.models.config import ProsodyConfig
from hume.error.hume_client_exception import HumeClientException
from env_keys import get_hume_api_key
import matplotlib.pyplot as plt

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set up your API key and configuration
hume_api_key = get_hume_api_key()

# Perform Hume emotion analysis on a given audio file
async def analyze_audio(file_path):
    client = HumeStreamClient(hume_api_key)
    config = ProsodyConfig()

    retries = 3
    for attempt in range(retries):
        try:
            async with client.connect([config]) as socket:
                result = await socket.send_file(file_path)
                return result
        except HumeClientException as e:
            logger.error(f"Error during audio analysis (attempt {attempt + 1}): {e}")
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                logger.error("Exceeded maximum retries for audio analysis.")
                return None

# Plot emotional analysis over time
def plot_emotions_over_time(prosody_data, file_name):
    if not prosody_data:
        print(f"No prosody data to plot for {file_name}.")
        return

    emotions_over_time = []
    emotion_labels = []

    for entry in prosody_data:
        for prediction in entry.get("predictions", []):
            emotions_over_time.append(prediction)
            if not emotion_labels:
                emotion_labels = prediction.keys()

    if not emotions_over_time or not emotion_labels:
        print(f"No emotions data available for plotting for {file_name}.")
        return

    time_points = range(len(emotions_over_time))

    plt.figure(figsize=(14, 8))
    for emotion in emotion_labels:
        values = [emo_data.get(emotion, 0) for emo_data in emotions_over_time]
        plt.plot(time_points, values, label=emotion)

    plt.xlabel("Time (5-second intervals)")
    plt.ylabel("Emotion Intensity")
    plt.title(f"Emotion Analysis Over Time for {file_name}")
    plt.legend()
    plt.show()

# Main function to process all WAV files in a folder
async def process_audio_folder(folder_path):
    wav_files = [f for f in os.listdir(folder_path) if f.endswith('.wav')]
    if not wav_files:
        print("No WAV files found in the specified folder.")
        return

    for wav_file in wav_files:
        file_path = os.path.join(folder_path, wav_file)
        print(f"Processing file: {file_path}")
        analysis_result = await analyze_audio(file_path)
        if analysis_result:
            prosody_data = analysis_result.get("prosody", [])
            plot_emotions_over_time(prosody_data, wav_file)
        else:
            print(f"Failed to analyze audio for {wav_file}.")

if __name__ == "__main__":
    # Change this path to the appropriate folder containing your WAV files
    wav_folder_path = "/Users/Parzon/Downloads/Artificial_Consciousness/InteractiveAvatarNextJSDemo-main/HeyGenPersonalised/uploaded_audio"
    loop = asyncio.get_event_loop()
    loop.run_until_complete(process_audio_folder(wav_folder_path))
