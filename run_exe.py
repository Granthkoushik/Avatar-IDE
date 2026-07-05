import threading
import time
import httpx
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent))
from app.main import app

def start_server():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)

if __name__ == "__main__":
    # Start FastAPI server in a background thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Wait for the server to be ready (simple health check)
    for _ in range(30):
        try:
            r = httpx.get("http://127.0.0.1:8000/api/health", timeout=1.0)
            if r.status_code == 200:
                break
        except Exception:
            time.sleep(0.5)

    # Open a native window using pywebview instead of the default browser
    import webview
    webview.create_window("Avatar IDE", "http://127.0.0.1:8000", width=1024, height=768)
    webview.start()

    # Keep the main thread alive until the server exits (Ctrl‑C)
    server_thread.join()
