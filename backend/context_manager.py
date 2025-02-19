# context_manager.py
import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConversationMemory:
    def __init__(self, max_length=10):
        self.conversations = []  # Each entry: (timestamp, user_input, ai_response)
        self.max_length = max_length

    def add_interaction(self, user_input: str, ai_response: str):
        timestamp = datetime.datetime.now().isoformat()
        self.conversations.append((timestamp, user_input, ai_response))
        if len(self.conversations) > self.max_length:
            self.summarize_history()

    def get_history(self):
        return self.conversations

    def summarize_history(self):
        # Placeholder for an actual summarization algorithm.
        removed = self.conversations.pop(0)
        logger.info(f"Summarized (and removed) oldest conversation: {removed}")

    def clear(self):
        self.conversations = []
