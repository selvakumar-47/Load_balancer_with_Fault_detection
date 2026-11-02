import threading
from typing import Optional, Dict, Any, List
from flask import Request, Response
from core.server_registry import ServerRegistry
from core.algorithms import AlgorithmFactory, LoadBalancingAlgorithm
from core.health_monitor import HealthMonitor
from core.proxy import ReverseProxy
from database.db import query_db, execute_db
from config import Config

class LoadBalancer:
    """
    Central Load Balancer coordinator.
    Routes requests across eligible backends, manages algorithms, health monitoring, and proxying.
    """
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or Config.DATABASE_PATH
        self.registry = ServerRegistry(self.db_path)
        self.proxy = ReverseProxy(self.registry, self.db_path)
        
        # Load active algorithm from DB config
        row = query_db("SELECT value FROM system_config WHERE key = 'active_algorithm';", one=True, db_path=self.db_path)
        algo_name = row["value"] if row else Config.DEFAULT_ALGORITHM
        self._algo_name = algo_name
        self._algorithm: LoadBalancingAlgorithm = AlgorithmFactory.create(algo_name)
        
        self.health_monitor = HealthMonitor(self.registry)
        self._lock = threading.Lock()

    def start(self):
        """Starts background health prober."""
        self.health_monitor.start()

    def stop(self):
        """Stops background health prober."""
        self.health_monitor.stop()

    def set_algorithm(self, algorithm_name: str) -> str:
        """Changes the active load balancing algorithm and persists choice."""
        with self._lock:
            algo = AlgorithmFactory.create(algorithm_name)
            self._algorithm = algo
            self._algo_name = algorithm_name.upper().replace("-", "_").replace(" ", "_")
            execute_db(
                "UPDATE system_config SET value = ?, updated_at = datetime('now', 'localtime') WHERE key = 'active_algorithm';",
                (self._algo_name,),
                db_path=self.db_path
            )
            return self._algo_name

    def get_algorithm_name(self) -> str:
        with self._lock:
            return self._algo_name

    def route_request(self, flask_req: Request, subpath: str, experiment_id: Optional[str] = None) -> Response:
        """
        Main entry point for incoming proxied requests.
        Selects an eligible backend and forwards request.
        """
        with self._lock:
            eligible_backends = self.registry.get_eligible_servers()
            selected_backend = self._algorithm.select_backend(eligible_backends) if eligible_backends else None
            algo_name = self._algo_name

        return self.proxy.forward_request(
            flask_req=flask_req,
            subpath=subpath,
            selected_backend=selected_backend,
            algorithm_name=algo_name,
            experiment_id=experiment_id
        )

    def get_stats_overview(self) -> Dict[str, Any]:
        """Calculates real-time overview metrics for the dashboard."""
        all_servers = self.registry.get_all_servers()
        total_servers = len(all_servers)
        healthy_count = sum(1 for s in all_servers if s.get("status") == "HEALTHY" and s.get("circuit_state") == "CLOSED")
        unhealthy_count = sum(1 for s in all_servers if s.get("status") == "UNHEALTHY" or s.get("circuit_state") == "OPEN")
        recovering_count = sum(1 for s in all_servers if s.get("circuit_state") == "HALF-OPEN")
        open_circuits = sum(1 for s in all_servers if s.get("circuit_state") == "OPEN")

        # Query request totals from request_logs
        stats_row = query_db(
            """SELECT 
                 COUNT(*) as total_reqs,
                 SUM(CASE WHEN is_success = 1 THEN 1 ELSE 0 END) as successful_reqs,
                 SUM(CASE WHEN is_success = 0 THEN 1 ELSE 0 END) as failed_reqs,
                 AVG(response_time_ms) as avg_latency
               FROM request_logs;""",
            one=True,
            db_path=self.db_path
        ) or {}

        total_reqs = stats_row.get("total_reqs", 0) or 0
        successful_reqs = stats_row.get("successful_reqs", 0) or 0
        failed_reqs = stats_row.get("failed_reqs", 0) or 0
        avg_latency = stats_row.get("avg_latency", 0.0) or 0.0
        success_rate = round((successful_reqs / total_reqs * 100.0), 1) if total_reqs > 0 else 100.0

        # Availability: % of healthy servers
        availability = round((healthy_count / total_servers * 100.0), 1) if total_servers > 0 else 0.0

        return {
            "total_servers": total_servers,
            "healthy_servers": healthy_count,
            "unhealthy_servers": unhealthy_count,
            "recovering_servers": recovering_count,
            "open_circuits": open_circuits,
            "total_requests": total_reqs,
            "successful_requests": successful_reqs,
            "failed_requests": failed_reqs,
            "success_rate": success_rate,
            "avg_response_time_ms": round(avg_latency, 2),
            "availability_percentage": availability,
            "active_algorithm": self._algo_name,
            "health_monitor": self.health_monitor.get_status()
        }
