from gtts import gTTS
import uuid
import os

def generate_speech(text: str) -> str:
    filename = f"audio_{uuid.uuid4().hex}.mp3"
    filepath = os.path.join("static", filename)

    tts = gTTS(text=text, lang='en')
    tts.save(filepath)

    return filepath
