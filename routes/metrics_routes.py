from flask import Blueprint, request, jsonify, Response
from core.metrics import MetricsEngine
from database.db import query_db

def create_metrics_blueprint(load_balancer):
    bp = Blueprint("metrics", __name__, url_prefix="/api")
    metrics_engine = MetricsEngine(load_balancer.db_path)

    @bp.route("/metrics/recovery-intelligence", methods=["GET"])
    def recovery_intelligence():
        """Returns deep recovery metrics: detection latency, recovery duration, failover continuity."""
        exp_id = request.args.get("experiment_id")
        data = metrics_engine.get_recovery_intelligence_metrics(exp_id)
        return jsonify(data), 200

    @bp.route("/metrics/export/csv", methods=["GET"])
    def export_csv():
        """Exports data to CSV format for requests, faults, or transitions."""
        data_type = request.args.get("type", "requests")
        csv_data = metrics_engine.export_csv(data_type)
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment;filename=lb_{data_type}_export.csv"}
        )

    @bp.route("/logs/requests", methods=["GET"])
    def list_request_logs():
        """Searchable and filterable request logs."""
        backend = request.args.get("backend")
        status = request.args.get("status")
        limit = min(500, int(request.args.get("limit", 100)))
        offset = int(request.args.get("offset", 0))

        query = "SELECT * FROM request_logs WHERE 1=1"
        params = []
        if backend:
            query += " AND selected_backend_id = ?"
            params.append(backend)
        if status == "success":
            query += " AND is_success = 1"
        elif status == "failure":
            query += " AND is_success = 0"

        query += " ORDER BY id DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        rows = query_db(query, tuple(params), db_path=load_balancer.db_path)
        return jsonify({"logs": rows, "count": len(rows)}), 200

    @bp.route("/logs/transitions", methods=["GET"])
    def list_transitions():
        """Lists circuit breaker transition events."""
        limit = min(200, int(request.args.get("limit", 50)))
        rows = query_db(
            """SELECT ct.*, s.name as server_name 
               FROM circuit_transitions ct
               LEFT JOIN servers s ON ct.server_id = s.id
               ORDER BY ct.id DESC LIMIT ?;""",
            (limit,),
            db_path=load_balancer.db_path
        )
        return jsonify({"transitions": rows, "count": len(rows)}), 200

    @bp.route("/logs/health", methods=["GET"])
    def list_health_probes():
        """Lists health monitor probe logs."""
        server_id = request.args.get("server_id")
        limit = min(200, int(request.args.get("limit", 50)))
        query = "SELECT * FROM health_history"
        params = []
        if server_id:
            query += " WHERE server_id = ?"
            params.append(server_id)
        query += " ORDER BY id DESC LIMIT ?;"
        params.append(limit)

        rows = query_db(query, tuple(params), db_path=load_balancer.db_path)
        return jsonify({"health_history": rows, "count": len(rows)}), 200

    return bp
