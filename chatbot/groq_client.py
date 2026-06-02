import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()


def get_groq_client():

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        return None

    client = Groq(
        api_key=api_key
    )

    return client