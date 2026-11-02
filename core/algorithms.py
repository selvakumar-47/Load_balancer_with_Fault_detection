import threading
from typing import List, Optional, Dict, Any

class LoadBalancingAlgorithm:
    """Base class for load balancing scheduling algorithms."""
    def select_backend(self, backends: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

class RoundRobinAlgorithm(LoadBalancingAlgorithm):
    """
    Standard Round Robin distribution.
    Thread-safe counter cycles through the list of eligible backends.
    """
    def __init__(self):
        self._index = 0
        self._lock = threading.Lock()

    def select_backend(self, backends: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not backends:
            return None
        with self._lock:
            selected = backends[self._index % len(backends)]
            self._index = (self._index + 1) % max(1, len(backends))
            return selected

class WeightedRoundRobinAlgorithm(LoadBalancingAlgorithm):
    """
    Smooth Weighted Round Robin (Nginx style algorithm).
    Provides smooth interleaved distribution across backends according to configured weights.
    Avoids clustering bursts on highest weighted server.
    """
    def __init__(self):
        self._current_weights: Dict[str, int] = {}
        self._lock = threading.Lock()

    def select_backend(self, backends: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not backends:
            return None

        with self._lock:
            # Ensure all backends are present in current weights tracker
            valid_ids = {b["id"] for b in backends}
            # Clean up obsolete backends
            self._current_weights = {k: v for k, v in self._current_weights.items() if k in valid_ids}

            total_weight = 0
            best_backend = None
            best_weight = -float("inf")

            for backend in backends:
                b_id = backend["id"]
                weight = max(1, int(backend.get("weight", 1)))
                total_weight += weight

                current = self._current_weights.get(b_id, 0) + weight
                self._current_weights[b_id] = current

                if current > best_weight:
                    best_weight = current
                    best_backend = backend

            if best_backend:
                b_id = best_backend["id"]
                self._current_weights[b_id] -= total_weight

            return best_backend

class LeastConnectionsAlgorithm(LoadBalancingAlgorithm):
    """
    Least Connections algorithm.
    Selects the backend currently serving the fewest active concurrent requests.
    Ties are broken by lowest average response time, then Round Robin.
    """
    def __init__(self):
        self._tie_breaker = 0
        self._lock = threading.Lock()

    def select_backend(self, backends: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not backends:
            return None

        with self._lock:
            # Sort by active_connections ascending, then last_response_time_ms ascending
            # For backends with equal active connections, rotate using tie breaker
            min_conns = min(b.get("active_connections", 0) for b in backends)
            candidates = [b for b in backends if b.get("active_connections", 0) == min_conns]

            if len(candidates) == 1:
                return candidates[0]

            # Break tie using round robin over candidates
            selected = candidates[self._tie_breaker % len(candidates)]
            self._tie_breaker = (self._tie_breaker + 1) % len(candidates)
            return selected

class AlgorithmFactory:
    """Factory and registry for load balancing algorithms."""
    _algorithms = {
        "ROUND_ROBIN": RoundRobinAlgorithm,
        "WEIGHTED_ROUND_ROBIN": WeightedRoundRobinAlgorithm,
        "LEAST_CONNECTIONS": LeastConnectionsAlgorithm
    }

    @classmethod
    def create(cls, algorithm_name: str) -> LoadBalancingAlgorithm:
        normalized = algorithm_name.upper().replace("-", "_").replace(" ", "_")
        algo_class = cls._algorithms.get(normalized, RoundRobinAlgorithm)
        return algo_class()

    @classmethod
    def list_available(cls) -> List[str]:
        return list(cls._algorithms.keys())
