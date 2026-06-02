import os
import anthropic
from dotenv import load_dotenv

load_dotenv()


def get_claude_client():

    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        return None

    return anthropic.Anthropic(api_key=api_key)
