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
    AUDIO_FILE_EXT,
    UPLOAD_DIR,
    PROCESSED_DIR, 
    DB_FILE
)

from logger import logger

audio_file_counter = 0
processed_hashes = set()
silence_counter = 0
leftover_segment = AudioSegment.empty()
current_speech_chunks = []
current_speech_range = []


# Path to a single combined WAV file that accumulates all valid (non-duplicate) audio
COMBINED_WAV_PATH = os.path.join(PROCESSED_DIR, "combined_audio.wav")

# How many milliseconds of the combined WAV we've already split into chunks
combined_offset_ms = 0

async def handle_audio_upload(request):
    """
    1) Receives .webm audio.
    2) Saves it to UPLOAD_DIR.
    3) Processes in background (append to single combined WAV + do 5s chunking).
    """
    global audio_file_counter
    reader = await request.multipart()
    field = await reader.next()
    if not field:
        return web.Response(text="No audio file found", status=400)

    audio_file_counter += 1
    base_filename = f"audio_{audio_file_counter}"
    filename = base_filename + AUDIO_FILE_EXT
    save_path = os.path.join(UPLOAD_DIR, filename)

    # Save the incoming file
    async with aiofiles.open(save_path, 'wb') as f:
        while True:
            chunk = await field.read_chunk()
            if not chunk:
                break
            await f.write(chunk)

    logger.info(f"Audio file uploaded: {save_path}")
    # Process in background
    asyncio.create_task(process_uploaded_audio(save_path, base_filename))
    return web.Response(text="Audio uploaded successfully")


async def process_uploaded_audio(file_path, base_filename):
    """
    1) Check duplicate (server side). If duplicate => remove, return.
    2) Convert upload to WAV (16kHz mono).
    3) Append newly converted WAV to leftover_segment (in memory).
    4) While leftover_segment >= 5 seconds, export a 5-second chunk + process it.
    5) Remove original upload + temp WAV at the end.
    """
    import datetime

    global silence_counter, leftover_segment

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

            # 2) Convert to WAV
            wav_path = await convert_to_wav(file_path, base_filename)
            if not wav_path or not os.path.exists(wav_path):
                logger.error("WAV conversion failed. Removing original.")
                os.remove(file_path)
                return

            # Load new WAV into memory
            try:
                new_seg = AudioSegment.from_file(wav_path)
            except Exception as e:
                logger.error(f"Could not read newly converted WAV: {e}")
                os.remove(file_path)
                os.remove(wav_path)
                return

            # 3) Append to leftover_segment (in-memory)
            leftover_segment += new_seg

            # 4) While leftover >= 5s, export chunk and process
            while len(leftover_segment) >= CHUNK_SIZE_MS:  # 5000ms
                # Slice out the first 5s
                five_sec = leftover_segment[:CHUNK_SIZE_MS]
                # Remove that 5s from the front of leftover_segment
                leftover_segment = leftover_segment[CHUNK_SIZE_MS:]

                # Export this chunk as a temporary WAV file
                ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                chunk_name = f"{base_filename}_session_{session_id}_chunk_{ts}.wav"
                chunk_path = os.path.join(PROCESSED_DIR, chunk_name)
                five_sec.export(chunk_path, format='wav')

                logger.info(f"Created 5-second chunk: {chunk_path} (duration={len(five_sec)}ms)")

                # -- Process the chunk (silence detection, counters, etc.) --
                try:
                    seg = AudioSegment.from_file(chunk_path)
                except Exception as e:
                    logger.warning(f"Unreadable chunk {chunk_path}: {e}")
                    if os.path.exists(chunk_path):
                        os.remove(chunk_path)
                    continue

                dur = len(seg)
                if dur < MIN_AUDIO_DURATION_MS:
                    logger.info(f"Removing sub-min chunk {chunk_path} (duration={dur}ms)")
                    if os.path.exists(chunk_path):
                        os.remove(chunk_path)
                    continue

                # Check silence
                is_silent = await detect_silence(chunk_path)
                if is_silent:
                    silence_counter += 1
                    logger.info(f"Silent chunk detected. Counter: {silence_counter}")

                    base_noext, ext = os.path.splitext(chunk_path)
                    renamed_path = f"{base_noext}_silence{ext}"
                    try:
                        os.rename(chunk_path, renamed_path)
                        logger.info(f"Renamed silent chunk => {renamed_path}")
                        if os.path.exists(chunk_path):
                            os.remove(chunk_path)
                    except Exception as e:
                        logger.error(f"Could not rename silent chunk: {e}")

                    # If user was continuously speaking, now is the time to transcribe
                    if current_speech_chunks:
                        await transcribe_dynamic_chunks(current_speech_chunks, current_speech_range, session_id, db_conn)
                        current_speech_chunks.clear()
                        current_speech_range.clear()

                else:
                    # Reset silence counter since speech was detected
                    silence_counter = 0
                    current_speech_chunks.append(chunk_path)
                    current_speech_range.append(len(current_speech_chunks))


                    # ========== Silence Logic (1,2,4,6) ==========
                    if silence_counter == 1:
                        logger.info("User silent for 1 chunk. Transcribing...")
                        # Save the concatenated audio to a temporary file
                        temp_transcription_path = os.path.join(PROCESSED_DIR, f"temp_transcription_{session_id}.wav")
                        combined_audio.export(temp_transcription_path, format='wav')

                        # Transcribe using the saved file path
                        transcription = await transcribe_audio(temp_transcription_path)

                        # Remove temp file after transcription
                        if os.path.exists(temp_transcription_path):
                            os.remove(temp_transcription_path)

                        if transcription:
                            face_emotions = await retrieve_face_emotions(db_conn)
                            prompt = (
                                f"The user was silent. Face emotions: {face_emotions}.\n"
                                f"User's last transcript: {transcription}\n"
                                "Please generate a friendly, helpful response."
                            )
                            ai_resp = await generate_openai_response(prompt)
                            if ai_resp:
                                await save_conversation_data(db_conn, session_id,
                                                             transcription, ai_resp) # bug fix

                    elif silence_counter == 6:
                        logger.info("User silent for 6 chunks. Starting conversation.")
                        await handle_conversation_starter(session_id)

                    elif silence_counter == 12:
                        logger.info("User silent for 12 chunks. Calling user.")
                        hey_prompt = (
                            "User has been silent for 4 chunks (~20 seconds). "
                            "Politely ask if they're still there."
                        )
                        hey_resp = await generate_openai_response(hey_prompt)
                        if hey_resp:
                            await save_conversation_data(db_conn, session_id, 
                                                         "Are you there?", 
                                                         hey_resp) # bug fix
                            logger.info(f"Sent 'Hey are you there?' => {hey_resp}")

                    elif silence_counter == 20:
                        logger.info("User silent for 6 chunks (~30 seconds). Shutting down the app.")
                        os._exit(0)

            # 5) Cleanup original files
            if os.path.exists(file_path):
                os.remove(file_path)
            if os.path.exists(wav_path):
                os.remove(wav_path)

    except Exception as e:
        logger.error(f"Error in process_uploaded_audio: {e}")

# ------Dynamic Chunking------------

async def transcribe_dynamic_chunks(chunk_files, chunk_range, session_id, db_conn):
    """
    Dynamically concatenates all consecutive non-silent chunks before a silence,
    sends it for transcription, and records the chunk range in the database.
    """
    if not chunk_files:
        return
    
    # Concatenate all valid speech chunks
    combined_audio = AudioSegment.empty()
    for cf in chunk_files:
        try:
            seg = AudioSegment.from_file(cf)
            combined_audio += seg
        except Exception as e:
            logger.warning(f"Error reading chunk {cf}: {e}")

    # Transcribe the combined audio file (without saving it)
    # Save concatenated audio to a temporary file before transcription
    temp_transcription_path = os.path.join(PROCESSED_DIR, f"temp_transcription_{session_id}.wav")
    combined_audio.export(temp_transcription_path, format='wav')

    # Transcribe using the saved file path
    transcription = await transcribe_audio(temp_transcription_path)

    # Remove the temp file after transcription
    if os.path.exists(temp_transcription_path):
        os.remove(temp_transcription_path)

    if transcription:
        face_emotions = await retrieve_face_emotions(db_conn)
        prompt = (
            f"User spoke continuously for {len(chunk_files) * 5} seconds. "
            f"Face emotions: {face_emotions}.\n"
            f"Full transcript: {transcription}\n"
            "Provide a meaningful response with full context."
        )
        ai_resp = await generate_openai_response(prompt)
        if ai_resp:
            await save_conversation_data(
                db_conn, session_id, transcription, ai_resp, chunk_range
            ) # check initial moood

    logger.info(f"Transcribed speech chunks {chunk_range} successfully.")



async def append_wav_to_combined(new_wav_path):
    """
    Appends 'new_wav_path' to our single 'combined_audio.wav' (COMBINED_WAV_PATH).
    If 'combined_audio.wav' doesn't exist yet, just rename 'new_wav_path' to it.
    Otherwise, load both, concatenate, and export.
    """
    if not os.path.exists(COMBINED_WAV_PATH):
        # Just rename the new file to be our combined file
        os.rename(new_wav_path, COMBINED_WAV_PATH)
        logger.info(f"Created initial combined WAV => {COMBINED_WAV_PATH}")
    else:
        def _append():
            combined_seg = AudioSegment.from_file(COMBINED_WAV_PATH)
            new_seg = AudioSegment.from_file(new_wav_path)
            final_seg = combined_seg + new_seg
            final_seg.export(COMBINED_WAV_PATH, format="wav")

        # Append in a background thread
        await asyncio.to_thread(_append)
        logger.info(f"Appended {new_wav_path} to {COMBINED_WAV_PATH}")

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
    """
    def _check():
        audio = AudioSegment.from_file(file_path, format="wav")
        silences = pydub_detect_silence(
            audio,
            min_silence_len=MIN_SILENCE_LEN,
            silence_thresh=SILENCE_THRESHOLD
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
    Convert the input audio file (e.g., .webm) to 16kHz mono WAV for Whisper.
    """
    def _conv():
        seg = AudioSegment.from_file(file_path)
        seg = seg.set_frame_rate(16000).set_channels(1)  # 16kHz mono
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
async def split_audio_into_chunks(
    file_path, base_filename, session_id, start_offset_ms=0
    ):
    """
    Splits the combined WAV from 'start_offset_ms' up to the end
    into exact 5s chunks. No padding is added. The leftover chunk
    (if any) is its real duration (could be < 5s).
    
    Returns the list of newly created chunk file paths.
    """
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
    if total_ms <= start_offset_ms:
        # No new audio to chunk
        return chunk_files

    # We'll slice only the new portion
    new_audio = audio[start_offset_ms:]

    new_len = len(new_audio)
    if new_len == 0:
        logger.warning("New portion of audio is 0 ms, skipping splitting.")
        return chunk_files

    # Full 5s chunks in the new portion
    num_full_chunks = new_len // CHUNK_SIZE_MS
    remainder = new_len % CHUNK_SIZE_MS

    # Create each 5-second chunk
    for i in range(num_full_chunks):
        start_ms = i * CHUNK_SIZE_MS
        seg = new_audio[start_ms:start_ms + CHUNK_SIZE_MS]
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        chunk_name = f"{base_filename}_session_{session_id}_chunk_{i}_{ts}.wav"
        chunk_path = os.path.join(PROCESSED_DIR, chunk_name)
        seg.export(chunk_path, format='wav')
        logger.info(
            f"Created chunk: {chunk_path} (duration={len(seg)}ms) "
            f"overall range=[{start_offset_ms + start_ms}, {start_offset_ms + start_ms + CHUNK_SIZE_MS}]"
        )
        chunk_files.append(chunk_path)

    # Leftover chunk (< 5s, no padding)
    if remainder > 0:
        leftover_start = num_full_chunks * CHUNK_SIZE_MS
        leftover_seg = new_audio[leftover_start:]
        leftover_dur = len(leftover_seg)
        if leftover_dur > 0:
            ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            chunk_name = f"{base_filename}_session_{session_id}_chunk_{num_full_chunks}_{ts}.wav"
            chunk_path = os.path.join(PROCESSED_DIR, chunk_name)
            leftover_seg.export(chunk_path, format='wav')
            logger.info(
                f"Created leftover chunk: {chunk_path} "
                f"(duration={leftover_dur}ms, no padding). "
                f"overall range=[{start_offset_ms + leftover_start}, {start_offset_ms + leftover_start + leftover_dur}]"
            )
            chunk_files.append(chunk_path)

    return chunk_files
    """
    Splits the given WAV file into exact 5-second chunks (CHUNK_SIZE_MS).
    NO leftover padding is applied; if there's leftover < CHUNK_SIZE_MS,
    we simply export that leftover "as is" without adding silence.
    """
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

    # How many full 5-second chunks we have
    num_full_chunks = total_ms // CHUNK_SIZE_MS
    remainder = total_ms % CHUNK_SIZE_MS

    # Export each 5-second chunk
    for i in range(num_full_chunks):
        start_ms = i * CHUNK_SIZE_MS
        seg = audio[start_ms:start_ms + CHUNK_SIZE_MS]
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        chunk_name = f"{base_filename}_session_{session_id}_chunk_{i}_{ts}.wav"
        chunk_path = os.path.join(PROCESSED_DIR, chunk_name)
        seg.export(chunk_path, format='wav')
        logger.info(f"Created chunk: {chunk_path} (duration={len(seg)}ms)")
        chunk_files.append(chunk_path)

    # Export leftover as-is (no padding)
    if remainder > 0:
        leftover_seg = audio[num_full_chunks * CHUNK_SIZE_MS:]
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        chunk_name = f"{base_filename}_session_{session_id}_chunk_{num_full_chunks}_{ts}.wav"
        chunk_path = os.path.join(PROCESSED_DIR, chunk_name)
        leftover_seg.export(chunk_path, format='wav')
        logger.info(
            f"Created leftover chunk: {chunk_path} "
            f"(duration={len(leftover_seg)}ms, no padding applied)"
        )
        chunk_files.append(chunk_path)

    return chunk_files