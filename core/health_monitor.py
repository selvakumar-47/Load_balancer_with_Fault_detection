import time
import threading
import requests
from typing import Optional
from core.server_registry import ServerRegistry
from config import Config

class HealthMonitor:
    """
    Background daemon thread that periodically probes backend servers.
    Detects failures and drives Circuit Breaker transitions independently of user traffic.
    """
    def __init__(self, registry: ServerRegistry, interval: Optional[float] = None, timeout: Optional[float] = None):
        self.registry = registry
        self.interval = interval or Config.HEALTH_CHECK_INTERVAL_SECONDS
        self.timeout = timeout or Config.HEALTH_CHECK_TIMEOUT_SECONDS
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_run_time: Optional[float] = None
        self._probe_count = 0

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="HealthMonitorThread", daemon=True)
        self._thread.start()
        print(f"[HealthMonitor] Started periodic health monitoring (interval: {self.interval}s, timeout: {self.timeout}s)")

    def stop(self):
        if not self._thread:
            return
        self._stop_event.set()
        self._thread.join(timeout=3.0)
        print("[HealthMonitor] Stopped")

    def _run_loop(self):
        # Initial short delay so servers can start up
        time.sleep(1.0)
        while not self._stop_event.is_set():
            try:
                self.probe_all_servers()
                self._last_run_time = time.time()
                self._probe_count += 1
            except Exception as e:
                print(f"[HealthMonitor Error in Run Loop] {e}")

            # Sleep in small slices to respond quickly to stop_event
            elapsed = 0.0
            slice_time = 0.2
            while elapsed < self.interval and not self._stop_event.is_set():
                time.sleep(slice_time)
                elapsed += slice_time

    def probe_all_servers(self):
        """Probes all registered servers concurrently or sequentially."""
        servers = self.registry.get_all_servers()
        threads = []
        for srv in servers:
            t = threading.Thread(target=self.probe_server, args=(srv,), daemon=True)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=self.timeout + 1.0)

    def probe_server(self, server: dict):
        """Probes an individual backend server /health endpoint."""
        server_id = server["id"]
        url = server["url"].rstrip("/") + "/health"
        start_time = time.time()

        try:
            resp = requests.get(
                url,
                timeout=self.timeout,
                headers={"User-Agent": "LoadBalancer-HealthProber/1.0"}
            )
            latency_ms = (time.time() - start_time) * 1000.0

            if 200 <= resp.status_code < 300:
                self.registry.record_health_check(
                    server_id=server_id,
                    is_healthy=True,
                    response_time_ms=latency_ms,
                    status_code=resp.status_code,
                    error_msg=None
                )
            else:
                self.registry.record_health_check(
                    server_id=server_id,
                    is_healthy=False,
                    response_time_ms=latency_ms,
                    status_code=resp.status_code,
                    error_msg=f"HTTP status {resp.status_code}"
                )
        except requests.exceptions.Timeout:
            latency_ms = (time.time() - start_time) * 1000.0
            self.registry.record_health_check(
                server_id=server_id,
                is_healthy=False,
                response_time_ms=latency_ms,
                status_code=None,
                error_msg=f"Health probe timed out (> {self.timeout}s)"
            )
        except requests.exceptions.ConnectionError as ce:
            latency_ms = (time.time() - start_time) * 1000.0
            self.registry.record_health_check(
                server_id=server_id,
                is_healthy=False,
                response_time_ms=latency_ms,
                status_code=None,
                error_msg="Connection refused (server down/unreachable)"
            )
        except Exception as ex:
            latency_ms = (time.time() - start_time) * 1000.0
            self.registry.record_health_check(
                server_id=server_id,
                is_healthy=False,
                response_time_ms=latency_ms,
                status_code=None,
                error_msg=str(ex)
            )

    def get_status(self) -> dict:
        return {
            "running": self._thread.is_alive() if self._thread else False,
            "interval_seconds": self.interval,
            "timeout_seconds": self.timeout,
            "probe_count": self._probe_count,
            "last_run_time": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self._last_run_time)) if self._last_run_time else None
        }
