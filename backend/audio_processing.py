import os
import asyncio
import aiofiles
import logging
import aiohttp
from pydub import AudioSegment
from pydub.silence import detect_silence

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AudioProcessor:
    def __init__(self, upload_dir="uploaded_audio", processed_dir="processed_audio"):
        self.upload_dir = upload_dir
        self.processed_dir = processed_dir
        self.silent_chunks = []  # Store silent chunks
        os.makedirs(upload_dir, exist_ok=True)
        os.makedirs(processed_dir, exist_ok=True)

    async def save_audio_file(self, file_data: bytes, filename: str) -> str:
        """
        Saves raw audio data to a file.
        """
        save_path = os.path.join(self.upload_dir, filename)
        async with aiofiles.open(save_path, 'wb') as f:
            await f.write(file_data)
        logger.info(f"Audio file saved: {save_path}")
        return save_path

    async def convert_to_wav(self, file_path: str) -> str:
        """
        Converts an audio file to WAV format.
        """
        def _convert():
            audio = AudioSegment.from_file(file_path)
            wav_path = file_path.rsplit(".", 1)[0] + ".wav"
            audio.export(wav_path, format="wav")
            return wav_path

        wav_file_path = await asyncio.to_thread(_convert)
        logger.info(f"Converted audio to WAV: {wav_file_path}")
        return wav_file_path

    async def detect_silence(self, file_path: str, min_silence_len=3000, silence_thresh=-40) -> bool:
        """
        Uses pydub to detect if a WAV file contains long segments of silence.
        - min_silence_len: Length in milliseconds to be considered silence
        - silence_thresh: Volume threshold to determine silence
        """
        def _detect():
            audio = AudioSegment.from_file(file_path, format="wav")
            silence_ranges = detect_silence(audio, min_silence_len=min_silence_len, silence_thresh=silence_thresh)
            return silence_ranges

        silence_ranges = await asyncio.to_thread(_detect)

        if silence_ranges:
            self.silent_chunks.append(file_path)
            logger.info(f"Silent chunk detected: {file_path}")
            return True  # Silence detected
        else:
            # If previous silent segments exist, merge them and send as one chunk
            if self.silent_chunks:
                logger.info("Merging silent audio segments before sending to transcription.")
                combined = sum([AudioSegment.from_file(chunk) for chunk in self.silent_chunks])
                final_chunk_path = os.path.join(self.upload_dir, "combined_silent.wav")
                combined.export(final_chunk_path, format="wav")
                self.silent_chunks = []  # Reset storage
                return False  # Not silent after merging
            return False  # Speech detected

    async def transcribe_audio(self, wav_file_path: str, openai_api_key: str, model="whisper-1") -> str:
        """
        Sends the WAV file to OpenAI’s Whisper API for transcription.
        - Returns text if successful, otherwise an empty string.
        """
        try:
            url = 'https://api.openai.com/v1/audio/transcriptions'
            headers = {'Authorization': f'Bearer {openai_api_key}'}
            form_data = aiohttp.FormData()

            async with aiofiles.open(wav_file_path, 'rb') as f:
                audio_data = await f.read()
                form_data.add_field('file', audio_data,
                                    filename=os.path.basename(wav_file_path),
                                    content_type='audio/wav')

            form_data.add_field('model', model)
            form_data.add_field('response_format', 'text')

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, data=form_data) as resp:
                    if resp.status == 200:
                        transcription = await resp.text()
                        logger.info(f"Transcription successful: {transcription.strip()}")
                        return transcription.strip()
                    else:
                        error_text = await resp.text()
                        logger.error(f"Transcription error: {resp.status} {error_text}")
                        return ""

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return ""
