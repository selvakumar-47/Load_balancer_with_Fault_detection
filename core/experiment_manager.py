import time
import uuid
import threading
import requests
from typing import Dict, Any, Optional
from database.db import query_db, execute_db
from config import Config

class ExperimentManager:
    """
    Manages controlled fault injections, synthetic workload generation,
    and automated failover experiment tracking.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, db_path: Optional[str] = None):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ExperimentManager, cls).__new__(cls)
                cls._instance.db_path = db_path or Config.DATABASE_PATH
                cls._instance.active_job = None
                cls._instance.stop_event = threading.Event()
            return cls._instance

    def inject_fault(self, server_id: str, fault_type: str, param_val: Optional[Any] = None) -> Dict[str, Any]:
        """
        Injects a fault into a registered local test backend and logs the fault injection event.
        Allowed fault_types: DELAY, ERROR_500, CRASH, RECOVER.
        """
        server = query_db("SELECT * FROM servers WHERE id = ?;", (server_id,), one=True, db_path=self.db_path)
        if not server:
            raise ValueError(f"Server {server_id} not found.")

        backend_url = server["url"].rstrip("/")
        event_id = f"fault-{uuid.uuid4().hex[:8]}"
        now_str = time.strftime('%Y-%m-%d %H:%M:%S')

        # Safety check: only allow localhost / 127.0.0.1
        if "127.0.0.1" not in backend_url and "localhost" not in backend_url:
            raise ValueError("Fault injection is restricted to local test backends only for safety.")

        try:
            if fault_type == "DELAY":
                ms = int(param_val) if param_val else 4000
                resp = requests.post(f"{backend_url}/fault/delay", json={"ms": ms}, timeout=2.0)
                details = f"Injected delay of {ms}ms (exceeds health timeout)"

            elif fault_type in ("ERROR_500", "ERROR"):
                code = int(param_val) if param_val else 500
                resp = requests.post(f"{backend_url}/fault/error", json={"code": code}, timeout=2.0)
                details = f"Injected HTTP {code} error responses"

            elif fault_type in ("CRASH", "DOWN"):
                resp = requests.post(f"{backend_url}/fault/crash", timeout=2.0)
                details = "Simulated backend process crash / unavailability"

            elif fault_type == "RECOVER":
                resp = requests.post(f"{backend_url}/fault/recover", timeout=2.0)
                details = "Triggered recovery to healthy state"

            else:
                raise ValueError(f"Unsupported fault type: {fault_type}")

            # Record in fault_events table
            execute_db(
                """INSERT INTO fault_events (event_id, server_id, fault_type, injected_at, status, details)
                   VALUES (?, ?, ?, ?, ?, ?);""",
                (event_id, server_id, fault_type, now_str, "ACTIVE", details),
                db_path=self.db_path
            )

            return {
                "event_id": event_id,
                "server_id": server_id,
                "fault_type": fault_type,
                "injected_at": now_str,
                "details": details,
                "backend_response": resp.json() if resp.status_code == 200 else resp.text
            }

        except Exception as e:
            raise RuntimeError(f"Failed to communicate with backend fault control endpoint at {backend_url}: {e}")

    def start_workload(
        self,
        target_lb_url: str,
        total_requests: int = 50,
        concurrency: int = 2,
        delay_ms: int = 50,
        algorithm_name: str = "ROUND_ROBIN"
    ) -> Dict[str, Any]:
        """Starts a background synthetic traffic batch against the load balancer."""
        with self._lock:
            if self.active_job and self.active_job.get("is_running"):
                raise RuntimeError("A workload experiment is already running. Please wait or stop it.")

            exp_id = f"exp-{uuid.uuid4().hex[:8]}"
            self.stop_event.clear()

            job_state = {
                "id": exp_id,
                "target_url": target_lb_url.rstrip("/") + "/proxy/",
                "total_requests": total_requests,
                "completed": 0,
                "successful": 0,
                "failed": 0,
                "distribution": {},
                "is_running": True,
                "start_time": time.time(),
                "end_time": None,
                "status": "RUNNING"
            }
            self.active_job = job_state

            # Record in SQLite experiments table
            execute_db(
                """INSERT INTO experiments (id, name, algorithm, total_requests, concurrency, delay_ms, status, start_time)
                   VALUES (?, ?, ?, ?, ?, ?, 'RUNNING', datetime('now', 'localtime'));""",
                (exp_id, f"Workload {exp_id}", algorithm_name, total_requests, concurrency, delay_ms),
                db_path=self.db_path
            )

            # Start worker thread
            worker = threading.Thread(
                target=self._run_workload_worker,
                args=(job_state, concurrency, delay_ms),
                daemon=True
            )
            worker.start()

            return {"message": "Workload experiment started", "experiment": job_state}

    def _run_workload_worker(self, job_state: dict, concurrency: int, delay_ms: int):
        total = job_state["total_requests"]
        target_url = job_state["target_url"]
        exp_id = job_state["id"]

        def send_single_req():
            if self.stop_event.is_set():
                return
            try:
                resp = requests.get(
                    target_url,
                    headers={"X-Experiment-ID": exp_id, "User-Agent": "LB-WorkloadGen/1.0"},
                    timeout=5.0
                )
                backend = resp.headers.get("X-Handled-By", "unknown")
                is_success = resp.status_code < 500
                with self._lock:
                    job_state["completed"] += 1
                    if is_success:
                        job_state["successful"] += 1
                    else:
                        job_state["failed"] += 1
                    job_state["distribution"][backend] = job_state["distribution"].get(backend, 0) + 1
            except Exception:
                with self._lock:
                    job_state["completed"] += 1
                    job_state["failed"] += 1
                    job_state["distribution"]["error"] = job_state["distribution"].get("error", 0) + 1

        for i in range(total):
            if self.stop_event.is_set():
                break
            send_single_req()
            if delay_ms > 0:
                time.sleep(delay_ms / 1000.0)

        with self._lock:
            job_state["is_running"] = False
            job_state["end_time"] = time.time()
            job_state["status"] = "STOPPED" if self.stop_event.is_set() else "COMPLETED"

            # Update DB experiment record
            success_rate = (
                round((job_state["successful"] / job_state["completed"]) * 100.0, 1)
                if job_state["completed"] > 0 else 0.0
            )
            execute_db(
                """UPDATE experiments
                   SET status = ?,
                       end_time = datetime('now', 'localtime'),
                       total_success = ?,
                       total_failed = ?,
                       success_rate = ?
                   WHERE id = ?;""",
                (
                    job_state["status"],
                    job_state["successful"],
                    job_state["failed"],
                    success_rate,
                    exp_id
                ),
                db_path=self.db_path
            )

    def stop_workload(self) -> Dict[str, Any]:
        """Signals active workload to abort gracefully."""
        self.stop_event.set()
        with self._lock:
            if self.active_job:
                self.active_job["is_running"] = False
                self.active_job["status"] = "STOPPED"
                return {"message": "Workload stopped", "experiment": self.active_job}
            return {"message": "No active workload found"}

    def get_workload_status(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if not self.active_job:
                return None
            return dict(self.active_job)
