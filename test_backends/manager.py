import sys
import os
import threading
import time
import requests
from werkzeug.serving import make_server
from test_backends.base_backend import create_backend_app

class BackendServerThread:
    def __init__(self, name: str, port: int):
        self.name = name
        self.port = port
        self.app = create_backend_app(name, port)
        self.server = None
        self.thread = None
        self.is_running = False

    def start(self):
        if self.is_running:
            return
        self.server = make_server("127.0.0.1", self.port, self.app, threaded=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.is_running = True
        print(f"[{self.name}] Started in thread on http://127.0.0.1:{self.port}")

    def stop(self):
        if not self.is_running or not self.server:
            return
        self.server.shutdown()
        self.thread.join(timeout=2.0)
        self.is_running = False
        print(f"[{self.name}] Stopped")

class BackendClusterManager:
    """Manages the 3 default local test backends."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(BackendClusterManager, cls).__new__(cls)
                cls._instance._servers = {
                    "srv-backend-a": BackendServerThread("Backend Alpha", 8001),
                    "srv-backend-b": BackendServerThread("Backend Beta", 8002),
                    "srv-backend-c": BackendServerThread("Backend Gamma", 8003),
                }
            return cls._instance

    def start_all(self):
        for srv in self._servers.values():
            if not srv.is_running:
                srv.start()

    def stop_all(self):
        for srv in self._servers.values():
            if srv.is_running:
                srv.stop()

    def start_server(self, server_id: str):
        if server_id in self._servers:
            self._servers[server_id].start()
            return True
        return False

    def stop_server(self, server_id: str):
        if server_id in self._servers:
            self._servers[server_id].stop()
            return True
        return False

    def restart_server(self, server_id: str):
        if server_id in self._servers:
            self.stop_server(server_id)
            time.sleep(0.5)
            self.start_server(server_id)
            return True
        return False

    def get_server_status(self, server_id: str):
        srv = self._servers.get(server_id)
        if not srv:
            return {"status": "UNKNOWN", "running": False}
        return {
            "name": srv.name,
            "port": srv.port,
            "running": srv.is_running
        }

    def get_all_status(self):
        return {s_id: self.get_server_status(s_id) for s_id in self._servers}

if __name__ == "__main__":
    manager = BackendClusterManager()
    print("Starting all 3 test backends...")
    manager.start_all()
    print("All backends running. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping test backends...")
        manager.stop_all()
        print("Done.")
