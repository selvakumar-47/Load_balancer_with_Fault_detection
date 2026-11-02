-- Schema for Load Balancer with Fault Detection and Automatic Recovery

CREATE TABLE IF NOT EXISTS servers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    weight INTEGER NOT NULL DEFAULT 1,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'HEALTHY', -- HEALTHY, DEGRADED, UNHEALTHY
    circuit_state TEXT NOT NULL DEFAULT 'CLOSED', -- CLOSED, OPEN, HALF-OPEN
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    consecutive_successes INTEGER NOT NULL DEFAULT 0,
    total_requests INTEGER NOT NULL DEFAULT 0,
    successful_requests INTEGER NOT NULL DEFAULT 0,
    failed_requests INTEGER NOT NULL DEFAULT 0,
    last_response_time_ms REAL NOT NULL DEFAULT 0.0,
    last_health_check TEXT,
    last_state_change TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS health_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    status TEXT NOT NULL, -- UP, DOWN, TIMEOUT, ERROR
    status_code INTEGER,
    response_time_ms REAL NOT NULL DEFAULT 0.0,
    error_message TEXT,
    FOREIGN KEY(server_id) REFERENCES servers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS circuit_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    reason TEXT NOT NULL,
    failure_count INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(server_id) REFERENCES servers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS request_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    selected_backend_id TEXT,
    selected_backend_url TEXT,
    algorithm_used TEXT NOT NULL,
    status_code INTEGER,
    response_time_ms REAL NOT NULL DEFAULT 0.0,
    is_success INTEGER NOT NULL, -- 1 for success, 0 for failure
    error_message TEXT,
    client_ip TEXT,
    experiment_id TEXT
);

CREATE TABLE IF NOT EXISTS fault_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    server_id TEXT NOT NULL,
    fault_type TEXT NOT NULL, -- DELAY, ERROR_500, CRASH, TIMEOUT
    injected_at TEXT NOT NULL,
    detected_at TEXT,
    detection_latency_ms REAL,
    recovered_at TEXT,
    recovery_duration_ms REAL,
    status TEXT NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, DETECTED, RECOVERING, RESOLVED
    details TEXT,
    FOREIGN KEY(server_id) REFERENCES servers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    algorithm TEXT NOT NULL,
    total_requests INTEGER NOT NULL,
    concurrency INTEGER NOT NULL DEFAULT 1,
    delay_ms INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'PENDING', -- PENDING, RUNNING, COMPLETED, STOPPED, FAILED
    start_time TEXT,
    end_time TEXT,
    fault_server_id TEXT,
    fault_type TEXT,
    fault_injected_at TEXT,
    fault_detected_at TEXT,
    fault_recovered_at TEXT,
    detection_time_ms REAL,
    recovery_time_ms REAL,
    total_success INTEGER NOT NULL DEFAULT 0,
    total_failed INTEGER NOT NULL DEFAULT 0,
    success_rate REAL NOT NULL DEFAULT 0.0,
    avg_latency_ms REAL NOT NULL DEFAULT 0.0,
    p95_latency_ms REAL NOT NULL DEFAULT 0.0,
    failover_continuity INTEGER NOT NULL DEFAULT 1,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS system_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Indexes for optimal querying
CREATE INDEX IF NOT EXISTS idx_health_history_server_time ON health_history(server_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_circuit_transitions_server_time ON circuit_transitions(server_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_request_logs_timestamp ON request_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_request_logs_backend ON request_logs(selected_backend_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_request_logs_experiment ON request_logs(experiment_id);
CREATE INDEX IF NOT EXISTS idx_fault_events_server ON fault_events(server_id, injected_at DESC);
