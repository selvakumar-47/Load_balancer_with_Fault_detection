import io
import csv
import math
from typing import Dict, List, Any, Optional
from database.db import query_db
from config import Config

class MetricsEngine:
    """Calculates operational and recovery intelligence metrics from SQLite."""
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or Config.DATABASE_PATH

    def get_dashboard_metrics(self) -> Dict[str, Any]:
        """Aggregates all metrics required for the overview dashboard charts and tables."""
        # 1. Server distribution
        dist_rows = query_db(
            """SELECT 
                 selected_backend_id,
                 COUNT(*) as count,
                 AVG(response_time_ms) as avg_latency,
                 SUM(CASE WHEN is_success = 1 THEN 1 ELSE 0 END) as success_count,
                 SUM(CASE WHEN is_success = 0 THEN 1 ELSE 0 END) as fail_count
               FROM request_logs
               WHERE selected_backend_id IS NOT NULL
               GROUP BY selected_backend_id;""",
            db_path=self.db_path
        )

        # 2. Recent response time & success trend (last 30 requests)
        trend_rows = query_db(
            """SELECT 
                 id,
                 timestamp,
                 response_time_ms,
                 is_success,
                 selected_backend_id,
                 status_code
               FROM request_logs
               ORDER BY id DESC
               LIMIT 30;""",
            db_path=self.db_path
        )
        trend_rows.reverse()

        # 3. Overall p95 response time calculation
        latencies = [r["response_time_ms"] for r in trend_rows if r["response_time_ms"] is not None]
        p95 = 0.0
        if latencies:
            latencies_sorted = sorted(latencies)
            idx = math.ceil(0.95 * len(latencies_sorted)) - 1
            p95 = round(latencies_sorted[max(0, idx)], 2)

        # 4. Recent fault events
        fault_rows = query_db(
            """SELECT * FROM fault_events ORDER BY id DESC LIMIT 10;""",
            db_path=self.db_path
        )

        # 5. Recent circuit transitions
        trans_rows = query_db(
            """SELECT ct.*, s.name as server_name 
               FROM circuit_transitions ct
               LEFT JOIN servers s ON ct.server_id = s.id
               ORDER BY ct.id DESC LIMIT 10;""",
            db_path=self.db_path
        )

        return {
            "distribution": dist_rows,
            "trend": trend_rows,
            "p95_latency_ms": p95,
            "recent_faults": fault_rows,
            "recent_transitions": trans_rows
        }

    def get_recovery_intelligence_metrics(self, experiment_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Deep fault detection and recovery intelligence metrics.
        Calculates exact detection latency, recovery time, failover continuity, and load redistribution.
        """
        where_clause = "WHERE experiment_id = ?" if experiment_id else ""
        params = (experiment_id,) if experiment_id else ()

        # Fault events with precise timings
        faults = query_db(
            """SELECT * FROM fault_events ORDER BY id DESC LIMIT 20;""",
            db_path=self.db_path
        )

        # Calculate averages for detected and resolved faults
        detected_faults = [f for f in faults if f["detection_latency_ms"] is not None]
        resolved_faults = [f for f in faults if f["recovery_duration_ms"] is not None]

        avg_detection_time = (
            round(sum(f["detection_latency_ms"] for f in detected_faults) / len(detected_faults), 2)
            if detected_faults else 0.0
        )
        avg_recovery_time = (
            round(sum(f["recovery_duration_ms"] for f in resolved_faults) / len(resolved_faults), 2)
            if resolved_faults else 0.0
        )

        # Circuit transitions summary
        transitions = query_db(
            """SELECT ct.*, s.name as server_name 
               FROM circuit_transitions ct
               LEFT JOIN servers s ON ct.server_id = s.id
               ORDER BY ct.id DESC LIMIT 25;""",
            db_path=self.db_path
        )

        # Traffic during experiment / overall
        req_query = f"""
            SELECT 
                selected_backend_id,
                COUNT(*) as total_requests,
                SUM(CASE WHEN is_success = 1 THEN 1 ELSE 0 END) as success_count,
                SUM(CASE WHEN is_success = 0 THEN 1 ELSE 0 END) as error_count,
                AVG(response_time_ms) as avg_latency
            FROM request_logs
            {where_clause}
            GROUP BY selected_backend_id;
        """
        traffic_distribution = query_db(req_query, params, db_path=self.db_path)

        # Failover continuity check: Did successful requests continue flowing when any server entered OPEN circuit?
        failover_continuity = True
        open_trans = [t for t in transitions if t["to_state"] == "OPEN"]
        if open_trans:
            # Check if there were successful requests timestamped around or after the open transition
            open_time = open_trans[0]["timestamp"]
            subsequent_successes = query_db(
                """SELECT COUNT(*) as cnt FROM request_logs 
                   WHERE timestamp >= ? AND is_success = 1;""",
                (open_time,),
                one=True,
                db_path=self.db_path
            )
            failover_continuity = bool(subsequent_successes and subsequent_successes["cnt"] > 0)

        return {
            "avg_detection_latency_ms": avg_detection_time,
            "avg_recovery_duration_ms": avg_recovery_time,
            "total_faults_tracked": len(faults),
            "detected_faults_count": len(detected_faults),
            "recovered_faults_count": len(resolved_faults),
            "failover_continuity": failover_continuity,
            "fault_events": faults,
            "circuit_transitions": transitions,
            "traffic_distribution": traffic_distribution
        }

    def export_csv(self, data_type: str) -> str:
        """Exports request logs, fault events, or circuit transitions as CSV string."""
        output = io.StringIO()
        writer = csv.writer(output)

        if data_type == "requests":
            rows = query_db("SELECT * FROM request_logs ORDER BY id DESC LIMIT 5000;", db_path=self.db_path)
            if rows:
                writer.writerow(rows[0].keys())
                for r in rows:
                    writer.writerow(r.values())
            else:
                writer.writerow(["id", "request_id", "timestamp", "method", "path", "selected_backend_id", "status_code", "response_time_ms", "is_success"])

        elif data_type == "faults":
            rows = query_db("SELECT * FROM fault_events ORDER BY id DESC LIMIT 1000;", db_path=self.db_path)
            if rows:
                writer.writerow(rows[0].keys())
                for r in rows:
                    writer.writerow(r.values())
            else:
                writer.writerow(["id", "event_id", "server_id", "fault_type", "injected_at", "detected_at", "detection_latency_ms", "recovered_at", "recovery_duration_ms", "status"])

        elif data_type == "transitions":
            rows = query_db("SELECT * FROM circuit_transitions ORDER BY id DESC LIMIT 1000;", db_path=self.db_path)
            if rows:
                writer.writerow(rows[0].keys())
                for r in rows:
                    writer.writerow(r.values())
            else:
                writer.writerow(["id", "server_id", "timestamp", "from_state", "to_state", "reason", "failure_count"])

        return output.getvalue()
