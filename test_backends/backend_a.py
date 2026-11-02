import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from test_backends.base_backend import create_backend_app

app = create_backend_app("Backend Alpha", 8001)

if __name__ == "__main__":
    print("[Backend Alpha] Starting on http://127.0.0.1:8001")
    app.run(host="127.0.0.1", port=8001, debug=False, threaded=True)
