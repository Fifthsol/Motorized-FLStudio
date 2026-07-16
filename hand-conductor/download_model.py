from pathlib import Path
import ssl
from urllib.error import URLError
from urllib.request import urlopen


MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/"
    "gesture_recognizer/float16/latest/gesture_recognizer.task"
)
MODEL_PATH = Path("models") / "gesture_recognizer.task"


def main() -> None:
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if MODEL_PATH.exists():
        print(f"Model already exists: {MODEL_PATH}")
        return

    print(f"Downloading MediaPipe Gesture Recognizer model to {MODEL_PATH}...")
    _download_file(MODEL_URL, MODEL_PATH)
    print("Done.")


def _download_file(url: str, path: Path) -> None:
    try:
        _download_file_with_context(url, path, context=None)
    except URLError as error:
        if not isinstance(error.reason, ssl.SSLCertVerificationError):
            raise
        print("Python SSL certificate verification failed; retrying model download without cert verification.")
        _download_file_with_context(url, path, context=ssl._create_unverified_context())


def _download_file_with_context(url: str, path: Path, context: ssl.SSLContext | None) -> None:
    with urlopen(url, context=context) as response:
        path.write_bytes(response.read())


if __name__ == "__main__":
    main()
