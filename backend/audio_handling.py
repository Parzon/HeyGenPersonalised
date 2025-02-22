import os
import asyncio
import aiofiles
import hashlib
import datetime
import aiosqlite

from aiohttp import web
from pydub import AudioSegment
from pydub.silence import detect_silence as pydub_detect_silence

from env_keys import get_openai_api_key, get_hume_api_key
from session_helpers import get_last_session_id, retrieve_face_emotions
from openai_configs import (
    generate_openai_response,
    handle_conversation_starter, 
    save_conversation_data, 
    transcribe_audio
)

from config import (
    SESSION_TIMEOUT,
    MAX_FILE_SIZE_MB,
    MIN_AUDIO_DURATION_MS,
    SILENCE_THRESHOLD,
    MIN_SILENCE_LEN,
    CHUNK_SIZE_MS,
    IMAGES_PER_BATCH,
    AUDIO_FILE_EXT
)

from logger import logger

async def handle_audio_upload(request):
    """
    Receives .webm audio, saves it with session/timestamp in name, then processes in background.
    """
    global audio_file_counter
    reader = await request.multipart()
    field = await reader.next()
    if not field:
        return web.Response(text="No audio file found", status=400)

    # We can embed session ID here if we want. We'll get it from DB (if any).
    # But we do that after we have the file. So let's just do a basic name now:
    audio_file_counter += 1
    base_filename = f"audio_{audio_file_counter}"
    filename = base_filename + AUDIO_FILE_EXT
    save_path = os.path.join(UPLOAD_DIR, filename)

    # Save
    async with aiofiles.open(save_path, 'wb') as f:
        while True:
            chunk = await field.read_chunk()
            if not chunk:
                break
            await f.write(chunk)

    logger.info(f"Audio file uploaded: {save_path}")
    asyncio.create_task(process_uploaded_audio(save_path, base_filename))
    return web.Response(text="Audio uploaded successfully")



async def process_uploaded_audio(file_path, base_filename):
    """
    1) Convert to valid WAV, split into 5s chunks (with leftover padded).
    2) For each chunk:
       - If it's unreadable or < MIN_AUDIO_DURATION_MS, remove it.
       - If silent, rename chunk file with _silence, and handle the 
         1,2,4,6 silence_counter logic:
           - 1 => Transcribe + face emotions => "friendly" response
           - 2 => handle_conversation_starter(session_id)
           - 4 => "Hey, are you there?"
           - 6 => shut down the app
       - Otherwise, reset silence_counter = 0.
    3) Remove the original .webm and the intermediate WAV at the end.
    """
    global silence_counter
    try:
        async with aiosqlite.connect(DB_FILE) as db_conn:
            session_id = await get_last_session_id(db_conn)
            if not session_id:
                logger.error("No session ID found in users. Cannot process audio.")
                return

            # 1) Duplicate check
            if await is_duplicate_audio(file_path):
                logger.info(f"Duplicate audio. Removing: {file_path}")
                os.remove(file_path)
                return

            # 2) Convert to WAV (16kHz mono)
            wav_path = await convert_to_wav(file_path, base_filename)
            if not wav_path or not os.path.exists(wav_path):
                logger.error("WAV conversion failed. Removing original file.")
                os.remove(file_path)
                return

            # 3) Split into 5s chunks (padding leftover to 5s)
            chunk_files = await split_audio_into_chunks(wav_path, base_filename, session_id)
            if not chunk_files:
                logger.info("No chunks. Removing original & wav.")
                os.remove(file_path)
                os.remove(wav_path)
                return

            short_or_bad = []

            # 4) Process each chunk for silence or validity
            for cf in chunk_files:
                # Attempt to read
                try:
                    seg = AudioSegment.from_file(cf)
                except Exception as e:
                    logger.warning(f"Unreadable chunk {cf}: {e}")
                    short_or_bad.append(cf)
                    continue

                dur = len(seg)
                if dur < MIN_AUDIO_DURATION_MS:
                    logger.info(f"Removing sub-min chunk {cf} (duration={dur}ms)")
                    short_or_bad.append(cf)
                    continue

                # Check silence
                is_silent = await detect_silence(cf)
                if is_silent:
                    silence_counter += 1
                    # Rename chunk with "_silence"
                    base_noext, ext = os.path.splitext(cf)
                    renamed_path = f"{base_noext}_silence{ext}"
                    try:
                        os.rename(cf, renamed_path)
                        cf = renamed_path
                        logger.info(f"Renamed silent chunk => {renamed_path}")
                    except Exception as e:
                        logger.error(f"Could not rename silent chunk: {e}")

                    # ========== Silence logic (1,2,4,6) ==========
                    if silence_counter == 1:
                        # 1 chunk of silence => transcribe => friendly response
                        transcription = await transcribe_audio(cf)
                        if transcription:
                            face_emotions = await retrieve_face_emotions(db_conn)
                            prompt = (
                                f"The user was silent. Face emotions: {face_emotions}.\n"
                                f"User's last transcript: {transcription}\n"
                                "Please generate a friendly, helpful response."
                            )
                            ai_resp = await generate_openai_response(prompt)
                            if ai_resp:
                                await save_conversation_data(db_conn, session_id, transcription, ai_resp)

                    elif silence_counter == 6:
                        # 2 silent chunks => conversation starter
                        await handle_conversation_starter(session_id)

                    elif silence_counter == 12:
                        # 4 silent chunks => "Hey, are you there?"
                        hey_prompt = "User has been silent for 4 chunks (~20 seconds). Politely ask if they're still there."
                        hey_resp = await generate_openai_response(hey_prompt)
                        if hey_resp:
                            await save_conversation_data(db_conn, session_id, "Are you there?", hey_resp)
                            logger.info(f"Sent 'Hey are you there?' => {hey_resp}")

                    elif silence_counter == 20:
                        # 6 silent chunks => shut down
                        logger.info("User silent for 6 chunks (~30 seconds). Shutting down the app.")
                        os._exit(0)

                else:
                    # Not silent => reset
                    silence_counter = 0

            # 5) Remove short/unusable chunks
            for badf in short_or_bad:
                if os.path.exists(badf):
                    os.remove(badf)
                    logger.info(f"Removed short/unusable chunk: {badf}")

            # 6) Clean up original .webm & .wav
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Removed original file: {file_path}")
            if os.path.exists(wav_path):
                os.remove(wav_path)
                logger.info(f"Removed intermediate WAV: {wav_path}")

    except Exception as e:
        logger.error(f"Error in process_uploaded_audio: {e}")

# -------------------- Short Chunk Combination --------------------

async def combine_short_chunks(chunk_files, base_filename, session_id):
    """
    If chunk is < 5s, combine with next chunk. 
    Return new list of chunk files, skipping none. 
    We do not delete or rename old files because we do not remove audio per your requirement.
    """
    if not chunk_files:
        return []

    segments = []
    for cf in chunk_files:
        try:
            seg = AudioSegment.from_file(cf)
            segments.append((cf, seg))
        except Exception as e:
            logger.warning(f"Error reading {cf}: {e}. Skipping it.")
            continue

    new_chunk_files = []
    i = 0
    while i < len(segments):
        cf, seg = segments[i]
        if len(seg) < CHUNK_SIZE_MS and i < len(segments) - 1:
            # Combine with next
            next_cf, next_seg = segments[i + 1]
            combined_seg = seg + next_seg
            out_name = f"{base_filename}_combined_{uuid.uuid4().hex}.wav"
            out_path = os.path.join(PROCESSED_DIR, out_name)
            combined_seg.export(out_path, format='wav')
            logger.info(f"Combined short chunk {cf} + {next_cf} => {out_path}")

            # Replace next with the newly combined segment
            segments[i + 1] = (out_path, combined_seg)
            # We keep the original chunk files on disk
            i += 1
        else:
            new_chunk_files.append(cf)
            i += 1

    return new_chunk_files

# -------------------- Duplicate Check --------------------

async def is_duplicate_audio(file_path):
    async with aiofiles.open(file_path, 'rb') as f:
        data = await f.read()
        audio_hash = hashlib.md5(data).hexdigest()

    if audio_hash in processed_hashes:
        logger.info(f"Duplicate audio detected: {file_path}")
        return True
    processed_hashes.add(audio_hash)
    return False

# -------------------- Silence Detection --------------------

async def detect_silence(file_path):
    """
    Return True if chunk is considered silent by pydub.
    We do a try/except in case ffmpeg fails.
    """
    def _check():
        audio = AudioSegment.from_file(file_path, format="wav")
        silences = pydub_detect_silence(
            audio, min_silence_len=MIN_SILENCE_LEN, silence_thresh=SILENCE_THRESHOLD
        )
        return len(silences) > 0

    try:
        return await asyncio.to_thread(_check)
    except Exception as e:
        logger.warning(f"Silence detection failed on {file_path}: {e}")
        return False

# -------------------- Audio Combination --------------------

async def combine_audio_chunks(chunk_files, base_filename):
    combined = AudioSegment.empty()
    for cf in chunk_files:
        try:
            seg = AudioSegment.from_file(cf)
            combined += seg
        except Exception as e:
            logger.warning(f"Error reading chunk {cf} during combine: {e}")
    out_name = f"{base_filename}_all_valid.wav"
    out_path = os.path.join(PROCESSED_DIR, out_name)
    combined.export(out_path, format='wav')
    logger.info(f"Combined valid chunks => {out_path}")
    return out_path

# -------------------- Audio Conversion --------------------

async def convert_to_wav(file_path, base_filename):
    """
    Convert the input audio file (e.g., .webm) to a valid 16kHz mono WAV format for OpenAI Whisper.
    """
    def _conv():
        seg = AudioSegment.from_file(file_path)
        seg = seg.set_frame_rate(16000).set_channels(1)  # Convert to 16kHz mono
        wav_name = f"{base_filename}.wav"
        wav_path = os.path.join(PROCESSED_DIR, wav_name)
        seg.export(wav_path, format='wav')
        return wav_path

    try:
        wav_path = await asyncio.to_thread(_conv)
        logger.info(f"✅ Converted {file_path} to {wav_path} (16kHz mono WAV)")
        return wav_path
    except Exception as e:
        logger.error(f"❌ Failed converting {file_path} to WAV: {e}")
        return None

# -------------------- Audio Splitting --------------------
async def split_audio_into_chunks(file_path, base_filename, session_id):
    chunk_files = []
    
    if not file_path or not os.path.exists(file_path):
        logger.error("No valid WAV file to split.")
        return chunk_files

    try:
        audio = AudioSegment.from_file(file_path)
    except Exception as e:
        logger.error(f"Cannot read WAV for splitting: {e}")
        return chunk_files

    total_ms = len(audio)
    if total_ms == 0:
        logger.warning(f"Audio file {file_path} is empty, skipping splitting.")
        return chunk_files

    num_full_chunks = total_ms // CHUNK_SIZE_MS
    remainder = total_ms % CHUNK_SIZE_MS

    for i in range(num_full_chunks):
        start_ms = i * CHUNK_SIZE_MS
        seg = audio[start_ms:start_ms + CHUNK_SIZE_MS]
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        chunk_name = f"{base_filename}_session_{session_id}_chunk_{i}_{ts}.wav"
        chunk_path = os.path.join(PROCESSED_DIR, chunk_name)
        seg.export(chunk_path, format='wav')
        logger.info(f"Created chunk: {chunk_path} (duration={len(seg)}ms)")
        chunk_files.append(chunk_path)

    if remainder > 0:
        leftover_seg = audio[num_full_chunks * CHUNK_SIZE_MS:]
        pad_duration = CHUNK_SIZE_MS - len(leftover_seg)
        padded_seg = leftover_seg + AudioSegment.silent(duration=pad_duration)
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        chunk_name = f"{base_filename}_session_{session_id}_chunk_{num_full_chunks}_{ts}.wav"
        chunk_path = os.path.join(PROCESSED_DIR, chunk_name)
        padded_seg.export(chunk_path, format='wav')
        logger.info(f"Created final padded chunk: {chunk_path} (original duration={len(leftover_seg)}ms, padded to 5000ms)")
        chunk_files.append(chunk_path)

    return chunk_files
