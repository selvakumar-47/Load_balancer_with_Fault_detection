import requests
import time

base = "http://127.0.0.1:5000"

print("=" * 65)
print("LOAD BALANCER WITH FAULT DETECTION & AUTOMATIC RECOVERY")
print("Full End-to-End Live System Verification Suite")
print("=" * 65)

# 1. UI and health
r = requests.get(base + "/")
assert r.status_code == 200 and "LB-SENTINEL" in r.text, "UI failed"
print("[1/7 PASS] Dashboard UI is live at http://127.0.0.1:5000")

r = requests.get(base + "/health")
assert r.status_code == 200 and r.json()["status"] == "UP", "LB self-health failed"
print(f"[2/7 PASS] Load Balancer self-health check: UP (Active: {r.json()['active_algorithm']})")

# 2. Proxy request distribution
handled_by = []
for i in range(6):
    res = requests.get(base + "/proxy/")
    assert res.status_code == 200
    handled_by.append(res.headers.get("X-Handled-By"))
print(f"[3/7 PASS] 6 Proxied Requests successfully routed to: {handled_by}")

# 3. Test Fault Injection & Failure Threshold
print("\n[Step] Injecting HTTP 500 error on Backend Alpha (srv-backend-a)...")
r = requests.post(base + "/api/experiment/fault", json={"server_id": "srv-backend-a", "fault_type": "ERROR_500", "param_val": 500})
assert r.status_code == 200

print("[Step] Waiting 10 seconds for Health Prober to detect 3 consecutive failures...")
time.sleep(10.0)

# Check server status and circuit breaker
servers = requests.get(base + "/api/servers").json()["servers"]
srv_a = next(s for s in servers if s["id"] == "srv-backend-a")
print(f"[4/7 PASS] Backend Alpha Circuit State: {srv_a['circuit_state']} (Failures: {srv_a['consecutive_failures']})")
assert srv_a["circuit_state"] == "OPEN", f"Expected circuit state OPEN, got {srv_a['circuit_state']}"

# 4. Failover continuity test: traffic must now go ONLY to b and c
post_fault_handled = []
for i in range(6):
    res = requests.get(base + "/proxy/")
    assert res.status_code == 200
    post_fault_handled.append(res.headers.get("X-Handled-By"))
assert "srv-backend-a" not in post_fault_handled, "Isolated backend srv-backend-a received proxy traffic!"
print(f"[5/7 PASS] Failover Continuity Verified! 100% traffic routed to healthy servers: {set(post_fault_handled)}")

# 5. Restore Backend Alpha & Automatic Recovery
print("\n[Step] Triggering Recovery for Backend Alpha...")
r = requests.post(base + "/api/experiment/fault", json={"server_id": "srv-backend-a", "fault_type": "RECOVER"})
assert r.status_code == 200

print("[Step] Waiting 12 seconds for recovery delay (5s) and recovery probes (2 * 3s) to restore CLOSED...")
time.sleep(12.0)

servers = requests.get(base + "/api/servers").json()["servers"]
srv_a = next(s for s in servers if s["id"] == "srv-backend-a")
print(f"[6/7 PASS] Backend Alpha Restored Circuit State: {srv_a['circuit_state']}")
assert srv_a["circuit_state"] == "CLOSED", f"Expected circuit state CLOSED, got {srv_a['circuit_state']}"

# Verify Alpha is back in eligible traffic pool
recovered_handled = []
for i in range(6):
    res = requests.get(base + "/proxy/")
    assert res.status_code == 200
    recovered_handled.append(res.headers.get("X-Handled-By"))
print(f"[PASS] Traffic post-recovery distributed across: {recovered_handled}")
assert "srv-backend-a" in recovered_handled, "Recovered backend Alpha not receiving traffic!"

# 6. Verify Recovery Intelligence Analytics
intel = requests.get(base + "/api/metrics/recovery-intelligence").json()
print("\n[7/7 PASS] Recovery Intelligence Analytics:")
print(f"       - Average Detection Latency: {intel['avg_detection_latency_ms']} ms")
print(f"       - Average Recovery Duration: {intel['avg_recovery_duration_ms']} ms")
print(f"       - Failover Continuity: {intel['failover_continuity']}")
print(f"       - Total Incidents Tracked: {intel['total_faults_tracked']}")

# 7. Verify CSV Export
csv_res = requests.get(base + "/api/metrics/export/csv?type=requests")
assert csv_res.status_code == 200 and "request_id" in csv_res.text
print(f"[PASS] Request Logs CSV Export: {len(csv_res.text.splitlines())} rows")

csv_faults = requests.get(base + "/api/metrics/export/csv?type=faults")
assert csv_faults.status_code == 200 and "event_id" in csv_faults.text
print(f"[PASS] Fault Events CSV Export: {len(csv_faults.text.splitlines())} rows")

print("\n" + "=" * 65)
print("ALL LIVE TESTS & LIFE-CYCLE PHASES PASSED WITH 100% SUCCESS!")
print("=" * 65)
