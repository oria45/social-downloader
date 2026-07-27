import threading
import time
import webbrowser

import uvicorn

from app.config import PORT
from app.main import app


def _open_browser_when_ready() -> None:
    time.sleep(1)
    webbrowser.open(f"http://127.0.0.1:{PORT}")


def main() -> None:
    # Pass the app object directly rather than the "app.main:app" string form -
    # PyInstaller's static import analysis needs a real `import` statement to
    # discover and bundle the app package; uvicorn's string-target loading is
    # a runtime dynamic import that PyInstaller can't see ahead of time.
    threading.Thread(target=_open_browser_when_ready, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=PORT)


if __name__ == "__main__":
    main()
