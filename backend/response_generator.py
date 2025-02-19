# response_generator.py
from openai import OpenAI
import logging
import asyncio
from env_keys import get_openai_api_key

# Get OpenAI API key
open_ai_key = get_openai_api_key()

# Debug mode (Set to False for production)
DEBUG = False

# Configure logging
logging.basicConfig(level=logging.DEBUG if DEBUG else logging.INFO)
logger = logging.getLogger(__name__)

class ResponseGenerator:
    def __init__(self, openai_api_key: str, model="gpt-4o"):
        self.client = OpenAI(api_key=openai_api_key)
        self.model = model

    async def generate_response(self, prompt: str, emotions=None, max_tokens=150):
        """
        Generates an AI response using streaming.

        :param prompt: User input text
        :param emotions: List of detected emotions (e.g., [{"emotion": "happy", "score": 0.85}])
        :param max_tokens: Max token limit for response
        :return: Async generator that yields response chunks
        """
        try:
            # Convert emotions into a readable string
            emotion_context = self._format_emotions(emotions)

            # Construct system message
            system_message = f"You are a compassionate AI assistant. The user appears {emotion_context}."

            if DEBUG:
                logger.debug(f"Generating response for prompt: '{prompt}' with emotion context: {emotion_context}")

            # OpenAI API Call (Streaming Mode)
            response_stream = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                stream=True
            )

            # Stream response chunks
            for chunk in response_stream:
                if chunk.choices and chunk.choices[0].delta:
                    text = chunk.choices[0].delta.content
                    if text:
                        yield text  # Stream response chunk

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            yield "I'm sorry, I couldn't process that."

    def _format_emotions(self, emotions):
        """
        Converts emotion data into a readable string for the AI.
        """
        if not emotions:
            return "neutral"
        
        # Sort by score (highest first) and get top emotion
        sorted_emotions = sorted(emotions, key=lambda e: e["score"], reverse=True)
        top_emotion = sorted_emotions[0]["emotion"]
        return f"{top_emotion} (confidence: {sorted_emotions[0]['score']:.2f})"
