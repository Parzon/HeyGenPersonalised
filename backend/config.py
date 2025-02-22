# config.py
SECRET_KEY = "b'\x9c!hV\xfa\xea\xba\xcf\x1a\x84s\xa0A\xa3\xbeodw\xd2\x92P6\xdb\xd9'"

DB_FILE = "/Users/Parzon/Downloads/Artificial_Consciousness/InteractiveAvatarNextJSDemo-main/HeyGenPersonalised/users.db"

UPLOAD_DIR = "uploaded_audio"

PROCESSED_DIR = "processed_audio"

IMAGE_DIR = "uploaded_images"

SESSION_TIMEOUT = 30           # Not used heavily, but kept

MAX_FILE_SIZE_MB = 25          # Not used in this snippet

MIN_AUDIO_DURATION_MS = 0      # Minimum duration for valid chunk

SILENCE_THRESHOLD = -40        # pydub silence threshold in dB

MIN_SILENCE_LEN = 4999         # Silence must be >= 4s

CHUNK_SIZE_MS = 5000           # Aim for 5-second chunks

IMAGES_PER_BATCH = 40          # Once 40 images have arrived, detect face

AUDIO_FILE_EXT = ".webm"       # Original uploads are .webm, converted to WAV
