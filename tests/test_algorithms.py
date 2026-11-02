import pytest
from core.algorithms import (
    RoundRobinAlgorithm,
    WeightedRoundRobinAlgorithm,
    LeastConnectionsAlgorithm,
    AlgorithmFactory
)

def test_round_robin_selection():
    algo = RoundRobinAlgorithm()
    backends = [
        {"id": "srv-a", "url": "http://127.0.0.1:8001"},
        {"id": "srv-b", "url": "http://127.0.0.1:8002"},
        {"id": "srv-c", "url": "http://127.0.0.1:8003"},
    ]

    # Test sequential cyclical selection
    selections = [algo.select_backend(backends)["id"] for _ in range(6)]
    assert selections == ["srv-a", "srv-b", "srv-c", "srv-a", "srv-b", "srv-c"]

def test_round_robin_empty():
    algo = RoundRobinAlgorithm()
    assert algo.select_backend([]) is None

def test_weighted_round_robin_distribution():
    algo = WeightedRoundRobinAlgorithm()
    # Alpha=3, Beta=2, Gamma=1 -> total weight = 6
    backends = [
        {"id": "srv-a", "weight": 3},
        {"id": "srv-b", "weight": 2},
        {"id": "srv-c", "weight": 1},
    ]

    selections = [algo.select_backend(backends)["id"] for _ in range(60)]
    counts = {"srv-a": selections.count("srv-a"), "srv-b": selections.count("srv-b"), "srv-c": selections.count("srv-c")}

    # Alpha should receive 30 (50%), Beta 20 (33.3%), Gamma 10 (16.7%)
    assert counts["srv-a"] == 30
    assert counts["srv-b"] == 20
    assert counts["srv-c"] == 10

def test_least_connections_selection():
    algo = LeastConnectionsAlgorithm()
    backends = [
        {"id": "srv-a", "active_connections": 5, "last_response_time_ms": 10},
        {"id": "srv-b", "active_connections": 1, "last_response_time_ms": 12},
        {"id": "srv-c", "active_connections": 3, "last_response_time_ms": 15},
    ]

    selected = algo.select_backend(backends)
    assert selected["id"] == "srv-b"

def test_least_connections_tie_breaker():
    algo = LeastConnectionsAlgorithm()
    backends = [
        {"id": "srv-a", "active_connections": 2, "last_response_time_ms": 10},
        {"id": "srv-b", "active_connections": 2, "last_response_time_ms": 10},
    ]

    first = algo.select_backend(backends)["id"]
    second = algo.select_backend(backends)["id"]
    # Should alternate across candidates with identical active connections
    assert first != second

def test_algorithm_factory():
    rr = AlgorithmFactory.create("ROUND_ROBIN")
    wrr = AlgorithmFactory.create("WEIGHTED_ROUND_ROBIN")
    lc = AlgorithmFactory.create("LEAST_CONNECTIONS")

    assert isinstance(rr, RoundRobinAlgorithm)
    assert isinstance(wrr, WeightedRoundRobinAlgorithm)
    assert isinstance(lc, LeastConnectionsAlgorithm)
