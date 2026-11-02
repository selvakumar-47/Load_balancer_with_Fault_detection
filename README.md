# Load Balancer with Fault Detection and Automatic Recovery
### Computer Science & Engineering (CSE) Mini-Project & Enterprise Operations Platform

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0%2B-green.svg)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/Database-SQLite3%20(WAL)-orange.svg)](https://sqlite.org/)
[![pytest](https://img.shields.io/badge/Tests-20%20Passed-brightgreen.svg)](https://pytest.org/)
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)](LICENSE)

---

## 1. Project Abstract & Objectives

Modern distributed web architectures rely heavily on load balancers to achieve high availability, fault tolerance, and horizontal scalability. However, standard load balancers often lack intelligent, localized circuit breakers, continuing to forward client requests to degrading instances until slow health checks trigger, leading to request timeouts and cascade failures.

This project implements a complete, full-stack **Load Balancer with Autonomous Fault Detection and Automatic Recovery (`LB-SENTINEL`)**. It features:

1. **RFC-Compliant Reverse Proxy**: Routes client HTTP requests through a central gateway (`:5000/proxy/*`), transparently proxying headers, query strings, and payloads while stripping hop-by-hop headers and tracking active concurrent requests.
2. **Deterministic Scheduling Algorithms**:
   - **Round Robin**: Modulo-based cyclical rotation across eligible servers.
   - **Weighted Round Robin**: Smooth deficit round-robin (Nginx algorithm) interleaving requests proportionally to server weights.
   - **Least Connections**: Dynamically routes traffic to the backend currently serving the fewest active requests.
3. **Autonomous 3-State Circuit Breaker Engine**:
   - `CLOSED`: Backend operates normally; client proxy traffic permitted.
   - `OPEN`: Repeated failures exceed threshold ($\ge 3$); backend is immediately isolated from client routing.
   - `HALF-OPEN`: After recovery delay timer elapses ($5.0\text{s}$), limited background probes test server stability.
   - Consecutive probe successes restore circuit to `CLOSED`.
4. **Independent Health Prober**: Dedicated daemon thread periodically probing `/health` endpoints without interfering with client traffic.
5. **Fault Detection and Recovery Intelligence Dashboard**:
   - Calculates empirical **Fault Detection Latency** ($T_{\text{detect}}$) from injection to circuit trip.
   - Calculates **Recovery Duration** ($T_{\text{recover}}$) from heal trigger to restored routing.
   - Verifies **Failover Continuity** (100% traffic continuity across healthy nodes during peer failure).
   - Computes real-time **p95 Latency** and response time distributions.
6. **Controlled Fault-Injection Lab**: Interactive laboratory allowing safe injection of latency delays, HTTP 500 errors, and simulated process crashes on 3 local test backends (Alpha: 8001, Beta: 8002, Gamma: 8003).
7. **Audit Logging & CSV Export**: Searchable request logs, circuit transitions, and one-click CSV export.

---

## 2. System Architecture

```
                    +------------------------------------+
                    |        Client Browser / Curl       |
                    +------------------------------------+
                                      |
                           HTTP Requests (/proxy/*)
                                      v
+-------------------------------------------------------------------------------+
|                      CENTRAL LOAD BALANCER (:5000)                             |
|                                                                               |
|  +-------------------------+     +-----------------------------------------+  |
|  |   Flask Reverse Proxy   | --> |            Server Registry              |  |
|  | - Strips Hop-by-Hop     |     | - SQLite with WAL concurrency           |  |
|  | - Active Conns Tracking |     | - Filters: Enabled & Circuit CLOSED     |  |
|  +-------------------------+     +-----------------------------------------+  |
|               |                                       ^                       |
|               v                                       |                       |
|  +-------------------------+                          |                       |
|  |  Scheduling Algorithm   | -------------------------+                       |
|  | - Round Robin           |                                                  |
|  | - Weighted Round Robin  |                                                  |
|  | - Least Connections     |                                                  |
|  +-------------------------+                                                  |
|               |                                                               |
|               | Dispatches Client Request                                     |
|               v                                                               |
|  +-------------------------------------------------------------------------+  |
|  |                    Circuit Breaker Engine (Per-Backend)                 |  |
|  |       [CLOSED] <--- 2 Recovery Probes --- [HALF-OPEN] <--- 5s Delay     |  |
|  |          |                                                    |         |  |
|  |          +-------- 3 Consecutive Failures -------> [OPEN] ----+         |  |
|  +-------------------------------------------------------------------------+  |
|                                       ^                                       |
|  +------------------------------------+                                       |
|  |     Background Health Monitor      | (Probes /health every 3.0s)           |
|  +------------------------------------+                                       |
+-------------------------------------------------------------------------------+
       |                                |                               |
       v                                v                               v
+----------------+              +----------------+              +----------------+
| Backend Alpha  |              |  Backend Beta  |              | Backend Gamma  |
| Port: 8001     |              |  Port: 8002    |              | Port: 8003     |
| Weight: 3      |              |  Weight: 2     |              | Weight: 1      |
+----------------+              +----------------+              +----------------+
```

---

## 3. Technology Stack

- **Backend Gateway**: Python 3.10+, Flask 3.0, Requests 2.31+, Werkzeug WSGI
- **Database & Persistence**: SQLite 3 with Write-Ahead Logging (`PRAGMA journal_mode = WAL`)
- **Frontend Console**: HTML5, Vanilla CSS3 (Design Tokens, Dark Enterprise Theme), Vanilla JavaScript (ES6+), Chart.js
- **Testing Suite**: pytest, unittest.mock

---

## 4. Directory Structure

```
load-balancer-fault-detection/
├── app.py                      # Main entry point, cluster startup, blueprint registration
├── config.py                   # Centralized configuration and security settings
├── requirements.txt            # Python dependencies (Flask, requests, pytest)
├── pytest.ini                  # Pytest configuration and pythonpath
├── conftest.py                 # Pytest root path fixture
├── verify_stack.py             # End-to-end live integration verification script
├── .env.example                # Example environment variables
├── README.md                   # Complete documentation and demo guide
├── database/
│   ├── db.py                   # Thread-safe SQLite connection factory with WAL mode
│   └── schema.sql              # Database schema, indexes, and tables
├── core/
│   ├── load_balancer.py        # Central Load Balancer coordinator
│   ├── algorithms.py           # Round Robin, Smooth Weighted Round Robin, Least Connections
│   ├── circuit_breaker.py      # CLOSED, OPEN, HALF-OPEN state machine
│   ├── health_monitor.py       # Daemon health checker probing /health
│   ├── proxy.py                # RFC reverse proxy with connection tracking
│   ├── server_registry.py      # Backend registry backed by SQLite
│   ├── metrics.py              # Aggregations, p95 latency, CSV export
│   └── experiment_manager.py   # Workload generation and fault injection manager
├── routes/
│   ├── proxy_routes.py         # /proxy/* reverse proxy and self-health /health
│   ├── server_routes.py        # CRUD APIs for backend servers & circuit overrides
│   ├── dashboard_routes.py     # Live overview metrics and chart series
│   ├── metrics_routes.py       # Recovery intelligence analytics and CSV export
│   ├── experiment_routes.py    # Controlled fault triggers and workload runner
│   └── settings_routes.py      # Threshold configuration and algorithm switcher
├── test_backends/
│   ├── base_backend.py         # Lightweight backend with /health and /fault/* endpoints
│   ├── backend_a.py            # Standalone runner for Alpha (:8001)
│   ├── backend_b.py            # Standalone runner for Beta (:8002)
│   ├── backend_c.py            # Standalone runner for Gamma (:8003)
│   └── manager.py              # Threaded cluster manager to control all 3 backends
├── templates/
│   └── index.html              # Enterprise Operations Console Single Page Application
├── static/
│   ├── css/
│   │   └── styles.css          # Design system, dark palette, responsive layout
│   ├── js/
│   │   └── app.js              # Real-time polling, charts, modals, and event handlers
│   └── vendor/
│       └── chart.min.js        # Local Chart.js bundle for offline operation
└── tests/
    ├── test_algorithms.py      # Algorithm unit tests
    ├── test_circuit_breaker.py # State machine transition tests
    ├── test_health_monitor.py  # Health check timeout and probe tests
    ├── test_proxy.py           # Reverse proxy, header stripping, and 503 tests
    ├── test_recovery.py        # Full fault isolation and automatic recovery test
    └── test_metrics.py         # p95 latency and CSV export tests
```

---

## 5. Installation & Execution Guide

### Prerequisites
- Python 3.10, 3.11, 3.12, or 3.13 installed.
- Windows, macOS, or Linux.

### Step 1: Clone or Navigate to Directory
```bash
cd c:\Users\Admin\OneDrive\Documents\min_project1
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Run the Complete Application
```bash
python app.py
```

*When started, the application automatically launches all 3 local test backends (`Alpha:8001`, `Beta:8002`, `Gamma:8003`), initializes the SQLite database, starts the background Health Monitor, and starts the Load Balancer on Port 5000.*

### Step 4: Open the Operations Console
Open your web browser and navigate to:
```
http://127.0.0.1:5000
```

### Deploy a Public Demo on Render

The repository includes a Render Blueprint in `render.yaml`. To deploy it:

1. Push the project to GitHub.
2. Sign in to [Render](https://render.com/) and choose **New → Blueprint**.
3. Connect the GitHub repository `selvakumar-47/Load_balancer_with_Fault_detection` and deploy the Blueprint.
4. Open the public URL Render provides for the web service.

The free service may sleep when idle and take a short time to wake up. Its local SQLite database is ephemeral, so data may be lost when the service restarts or redeploys. This demo has no login: anyone with its public URL can use the dashboard, change settings, and inject simulated faults. Do not use it for private data or production traffic.

---

## 6. Live Academic Demonstration Walkthrough

Follow this step-by-step procedure to demonstrate the full capabilities to an evaluator:

### Step 1: Verify Initial Healthy Fleet
1. In the **Overview Dashboard**, observe the 8 metric cards:
   - Healthy Servers: `3 / 3`
   - Fault / Isolated: `0 Open`
   - Availability: `100%`
2. Click **Send Test Request** in the top navigation bar multiple times.
3. Observe the response toast indicating requests being distributed across `srv-backend-a`, `srv-backend-b`, and `srv-backend-c`.

### Step 2: Test Scheduling Algorithms
1. Navigate to **Load Balancing** in the sidebar.
2. Switch the active algorithm from `Round Robin` to `Weighted Round Robin` (Alpha=3, Beta=2, Gamma=1) and click **Apply Algorithm**.
3. Navigate to **Fault-Injection Lab** and under **Synthetic Workload Traffic Generator**, click **Generate Load** (50 requests).
4. Observe the live progress bar and per-backend distribution pills: Alpha will serve ~50% of the requests, Beta ~33%, and Gamma ~17%.

### Step 3: Controlled Fault Injection & Circuit Tripping
1. In **Fault-Injection Lab**, locate the **Backend Alpha** card.
2. Click **Inject HTTP 500** (or **Inject 4s Delay**).
3. Switch to the **Circuit Breaker** view.
4. Watch the failure counter on Backend Alpha increase from `1` to `2` to `3`.
5. Upon reaching the failure threshold (3), the circuit breaker automatically trips to **OPEN**!
6. Backend Alpha's status badge flips to `UNHEALTHY`, and the Overview Dashboard shows `1 Open`.

### Step 4: Verify Failover Continuity (Zero 503 Errors)
1. While Backend Alpha is in `OPEN` circuit state, send another batch of requests (or click **Send Test Request** repeatedly).
2. Inspect the **Event Logs & CSV** view:
   - Notice that 100% of the requests continue to succeed through `srv-backend-b` and `srv-backend-c`.
   - Backend Alpha is completely isolated from routing, preventing user-facing timeouts.

### Step 5: Automatic Recovery Verification
1. Return to **Fault-Injection Lab** and click **Restore Health** on Backend Alpha.
2. Switch to **Circuit Breaker**:
   - After the recovery delay ($5.0\text{s}$) elapses, the state transitions to **HALF-OPEN**.
   - The Health Monitor sends controlled trial probes.
   - Upon completing 2 consecutive successful probes, the circuit restores to **CLOSED**!
3. Send requests again: Backend Alpha immediately resumes receiving its fair share of normal traffic.

### Step 6: Inspect Recovery Intelligence Analytics
1. Navigate to **Recovery Intelligence**:
   - Inspect **Average Detection Latency**: Shows exact milliseconds taken to detect the fault.
   - Inspect **Average Recovery Duration**: Shows elapsed duration until full traffic restoration.
   - Confirm **Failover Continuity**: Shows `100% Maintained`.
2. Click **Export Requests CSV** to download the collected metrics.

---

## 7. Running Automated Tests

Run the full automated test suite covering all 15 project test specifications:

```bash
pytest -v
```

### Test Coverage Highlights:
- `test_algorithms.py`: Round Robin, Smooth Weighted Round Robin, Least Connections, and Factory.
- `test_circuit_breaker.py`: CLOSED, OPEN, HALF-OPEN transitions, probe retry, and thresholds.
- `test_health_monitor.py`: Probe latency measurement, connection error, and timeout detection.
- `test_proxy.py`: Header stripping, active connection accounting, 503 handling, and SSRF security allowlists.
- `test_recovery.py`: End-to-end failover lifecycle, traffic exclusion, and recovery restoration.
- `test_metrics.py`: p95 latency calculation, recovery metrics, and CSV formatting.

---

## 8. REST API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/health` | `GET` | Load balancer self-health and active algorithm |
| `/proxy/<subpath>` | `ANY` | Reverse proxy forwarding client requests to eligible backends |
| `/api/servers` | `GET` | List all registered backend servers with live metrics |
| `/api/servers` | `POST` | Register a new backend server (URL validation enforced) |
| `/api/servers/<id>` | `PUT` | Update server weight, URL, or enabled status |
| `/api/servers/<id>` | `DELETE` | Deregister a backend server |
| `/api/servers/<id>/toggle` | `POST` | Enable or disable a backend |
| `/api/servers/<id>/circuit/trip` | `POST` | Manually trip circuit breaker to OPEN |
| `/api/servers/<id>/circuit/reset`| `POST` | Manually reset circuit breaker to CLOSED |
| `/api/algorithms` | `GET` | List available load-balancing algorithms |
| `/api/algorithm` | `POST` | Switch active load-balancing algorithm |
| `/api/dashboard/overview` | `GET` | Real-time overview counters, SLA availability, and probe counts |
| `/api/dashboard/metrics` | `GET` | Chart data (backend distribution, response time trend, p95) |
| `/api/metrics/recovery-intelligence` | `GET` | Detection latency, recovery duration, and failover continuity |
| `/api/metrics/export/csv` | `GET` | Export CSV logs (`?type=requests\|faults\|transitions`) |
| `/api/logs/requests` | `GET` | Searchable and filterable request routing logs |
| `/api/logs/transitions` | `GET` | Circuit breaker state change audit trail |
| `/api/experiment/fault` | `POST` | Inject controlled fault (`DELAY`, `ERROR_500`, `CRASH`, `RECOVER`) |
| `/api/experiment/workload/start` | `POST` | Start synthetic traffic workload batch |
| `/api/experiment/workload/stop` | `POST` | Abort running workload batch |
| `/api/experiment/workload/status` | `GET` | Query ongoing workload progress and distribution |
| `/api/settings` | `GET` / `POST` | View or tune timeouts, intervals, and thresholds |

---

## 9. Security & Reliability Highlights

1. **SSRF & Destination Allowlisting**: The reverse proxy strictly validates backend destination URLs against allowed local development hosts (`127.0.0.1`, `localhost`) and permitted port ranges (`8000-8010`, `5000-5010`). Arbitrary external URL forwarding is rejected with HTTP 400.
2. **RFC 7230 Hop-by-Hop Header Stripping**: Headers such as `Connection`, `Keep-Alive`, `Proxy-Authenticate`, `TE`, and `Upgrade` are stripped before forwarding to prevent connection desynchronization attacks.
3. **Thread Safety & Database Concurrency**:
   - Algorithms and circuit breakers use re-entrant locks (`threading.Lock` / `threading.RLock`).
   - SQLite uses thread-local connections with **Write-Ahead Logging (WAL)** enabled to prevent database locking during high-concurrency workloads.
4. **Single Point of Failure (SPOF) Disclaimer**: In this standalone mini-project, the load balancer runs as a single process. In production, redundancy is achieved via VRRP (Keepalived) or BGP Anycast IP failover.

---

## 10. Conclusion

`LB-SENTINEL` delivers a reliable, fully functioning load balancing and fault recovery system with enterprise-grade observability. It successfully demonstrates the complete fault-tolerance lifecycle—from deterministic request routing to autonomous fault isolation, probe-based recovery, and empirical performance analytics.
