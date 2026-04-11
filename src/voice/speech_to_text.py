import whisper

# model load once (important)
model = whisper.load_model("base")

def transcribe_audio(file_path: str) -> str:
    result = model.transcribe(file_path)
    return result["text"]
