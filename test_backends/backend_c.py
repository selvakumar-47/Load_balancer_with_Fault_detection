import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from test_backends.base_backend import create_backend_app

app = create_backend_app("Backend Gamma", 8003)

if __name__ == "__main__":
    print("[Backend Gamma] Starting on http://127.0.0.1:8003")
    app.run(host="127.0.0.1", port=8003, debug=False, threaded=True)
