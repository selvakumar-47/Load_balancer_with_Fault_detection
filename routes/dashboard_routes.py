from flask import Blueprint, jsonify
from core.metrics import MetricsEngine

def create_dashboard_blueprint(load_balancer):
    bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")
    metrics_engine = MetricsEngine(load_balancer.db_path)

    @bp.route("/overview", methods=["GET"])
    def overview():
        """Returns overview dashboard counters and system health."""
        stats = load_balancer.get_stats_overview()
        return jsonify(stats), 200

    @bp.route("/metrics", methods=["GET"])
    def dashboard_metrics():
        """Returns chart series data (distribution, trends, p95 latency, recent events)."""
        metrics = metrics_engine.get_dashboard_metrics()
        return jsonify(metrics), 200

    return bp
