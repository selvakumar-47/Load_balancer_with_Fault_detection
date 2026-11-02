// Load Balancer & Fault Recovery Console - Enterprise Frontend Engine

document.addEventListener('DOMContentLoaded', () => {
  // Global State
  let activeView = 'overview';
  let pollTimer = null;
  let workloadTimer = null;
  let distChart = null;
  let latencyChart = null;

  // Cache DOM Elements
  const navItems = document.querySelectorAll('.sidebar-nav .nav-item');
  const viewPanes = document.querySelectorAll('.view-pane');
  const pageTitleDisplay = document.getElementById('page-title-display');
  const headerAlgoName = document.getElementById('header-algo-name');
  const headerAvailDot = document.getElementById('header-avail-dot');
  const headerAvailText = document.getElementById('header-avail-text');
  const btnManualRefresh = document.getElementById('btn-manual-refresh');
  const btnQuickTraffic = document.getElementById('btn-quick-traffic');

  // Navigation Logic
  window.navigateTo = function(viewId) {
    activeView = viewId;
    navItems.forEach(item => {
      if (item.dataset.view === viewId) {
        item.classList.add('active');
        const viewName = item.textContent.trim();
        pageTitleDisplay.textContent = viewName;
      } else {
        item.classList.remove('active');
      }
    });

    viewPanes.forEach(pane => {
      pane.classList.toggle('active', pane.id === `view-${viewId}`);
    });

    // Immediate refresh on view switch
    refreshCurrentView();
  };

  navItems.forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      navigateTo(item.dataset.view);
    });
  });

  // Toast Notification System
  window.showToast = function(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  };

  // ==================== OVERVIEW DASHBOARD ====================
  async function fetchOverviewData() {
    try {
      const [resOverview, resMetrics] = await Promise.all([
        fetch('/api/dashboard/overview'),
        fetch('/api/dashboard/metrics')
      ]);

      if (!resOverview.ok || !resMetrics.ok) return;

      const overview = await resOverview.json();
      const metrics = await resMetrics.json();

      // Top Nav Badges
      headerAlgoName.textContent = overview.active_algorithm || 'ROUND_ROBIN';
      const avail = overview.availability_percentage || 0;
      headerAvailText.textContent = `${avail}% Availability`;
      if (avail > 66) {
        headerAvailDot.className = 'dot dot-healthy';
      } else if (avail > 0) {
        headerAvailDot.className = 'dot dot-warning';
      } else {
        headerAvailDot.className = 'dot dot-danger';
      }

      // 8 Metric Cards
      document.getElementById('card-healthy-val').textContent = `${overview.healthy_servers} / ${overview.total_servers}`;
      document.getElementById('card-total-servers').textContent = overview.total_servers;
      document.getElementById('card-unhealthy-val').textContent = overview.unhealthy_servers;
      document.getElementById('card-recovering-val').textContent = overview.recovering_servers;
      document.getElementById('card-unhealthy-badge').textContent = `${overview.open_circuits} Open`;
      document.getElementById('card-total-reqs').textContent = Number(overview.total_requests).toLocaleString();
      document.getElementById('card-successful-reqs').textContent = overview.successful_requests;
      document.getElementById('card-failed-reqs').textContent = overview.failed_requests;
      document.getElementById('card-success-rate').textContent = `${overview.success_rate}%`;
      document.getElementById('card-success-badge').textContent = overview.success_rate >= 95 ? 'Healthy' : 'Degraded';
      document.getElementById('card-avg-latency').textContent = `${overview.avg_response_time_ms} ms`;
      document.getElementById('card-p95-latency').textContent = `${metrics.p95_latency_ms || 0} ms`;
      document.getElementById('card-availability').textContent = `${overview.availability_percentage}%`;
      
      if (overview.health_monitor) {
        document.getElementById('card-probe-interval').textContent = `${overview.health_monitor.interval_seconds}s`;
        document.getElementById('card-probe-count').textContent = overview.health_monitor.probe_count || 0;
      }

      // Update Charts
      updateDistributionChart(metrics.distribution || []);
      updateLatencyChart(metrics.trend || []);

      // Update Overview Fleet Table
      fetchOverviewFleet();

      // Update Events Timeline
      renderOverviewTimeline(metrics.recent_transitions || [], metrics.recent_faults || []);

    } catch (err) {
      console.error('Error fetching overview data:', err);
    }
  }

  function updateDistributionChart(distData) {
    const ctx = document.getElementById('chart-distribution');
    if (!ctx) return;

    const labels = distData.map(d => d.selected_backend_id || 'Unknown');
    const counts = distData.map(d => d.count || 0);

    const colors = [
      '#3b82f6', // Alpha (Blue)
      '#10b981', // Beta (Green)
      '#f59e0b', // Gamma (Amber)
      '#8b5cf6', // Delta (Purple)
      '#ef4444'  // Error / Other
    ];

    if (!distChart) {
      distChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
          labels: labels.length ? labels : ['No Traffic Yet'],
          datasets: [{
            data: counts.length ? counts : [1],
            backgroundColor: counts.length ? colors.slice(0, labels.length) : ['#1e293b'],
            borderWidth: 1,
            borderColor: '#131b2e'
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { position: 'bottom', labels: { color: '#94a3b8', boxWidth: 12 } }
          }
        }
      });
    } else {
      distChart.data.labels = labels.length ? labels : ['No Traffic Yet'];
      distChart.data.datasets[0].data = counts.length ? counts : [1];
      distChart.data.datasets[0].backgroundColor = counts.length ? colors.slice(0, labels.length) : ['#1e293b'];
      distChart.update('none');
    }
  }

  function updateLatencyChart(trendData) {
    const ctx = document.getElementById('chart-latency-trend');
    if (!ctx) return;

    const labels = trendData.map((d, i) => `#${d.id || i + 1}`);
    const latencies = trendData.map(d => d.response_time_ms || 0);
    const pointColors = trendData.map(d => d.is_success ? '#10b981' : '#ef4444');

    if (!latencyChart) {
      latencyChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [{
            label: 'Latency (ms)',
            data: latencies,
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59, 130, 246, 0.1)',
            fill: true,
            tension: 0.3,
            pointBackgroundColor: pointColors,
            pointRadius: 4
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            x: { grid: { color: '#1e293b' }, ticks: { color: '#64748b' } },
            y: { grid: { color: '#1e293b' }, ticks: { color: '#64748b' }, beginAtZero: true }
          },
          plugins: {
            legend: { display: false }
          }
        }
      });
    } else {
      latencyChart.data.labels = labels;
      latencyChart.data.datasets[0].data = latencies;
      latencyChart.data.datasets[0].pointBackgroundColor = pointColors;
      latencyChart.update('none');
    }
  }

  async function fetchOverviewFleet() {
    try {
      const res = await fetch('/api/servers');
      if (!res.ok) return;
      const data = await res.json();
      const tbody = document.getElementById('overview-servers-tbody');
      if (!tbody) return;

      if (!data.servers || data.servers.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No backends registered.</td></tr>';
        return;
      }

      tbody.innerHTML = data.servers.map(s => `
        <tr>
          <td><strong>${s.name}</strong> <span class="mono" style="font-size: 11px; color: var(--text-muted);">(${s.id})</span></td>
          <td><span class="mono">${s.url}</span></td>
          <td>${getStatusBadge(s.status)}</td>
          <td>${getCircuitBadge(s.circuit_state)}</td>
          <td>${s.total_requests} req</td>
          <td>${s.last_response_time_ms || 0} ms</td>
        </tr>
      `).join('');
    } catch (err) {
      console.error(err);
    }
  }

  function renderOverviewTimeline(transitions, faults) {
    const timeline = document.getElementById('overview-events-timeline');
    if (!timeline) return;

    if (!transitions.length && !faults.length) {
      timeline.innerHTML = '<div class="empty-state">No circuit transitions or failure events recorded yet.</div>';
      return;
    }

    const items = transitions.slice(0, 6).map(t => {
      const isTrip = t.to_state === 'OPEN';
      const isRecover = t.to_state === 'CLOSED';
      const color = isTrip ? 'var(--color-danger)' : (isRecover ? 'var(--color-healthy)' : 'var(--color-warning)');
      return `
        <div class="timeline-item">
          <div class="timeline-marker" style="background-color: ${color}; box-shadow: 0 0 6px ${color};"></div>
          <div class="timeline-content">
            <div class="timeline-time">${t.timestamp} &bull; ${t.server_name || t.server_id}</div>
            <div class="timeline-text">
              Transitioned to <strong style="color: ${color};">${t.to_state}</strong>: ${t.reason}
            </div>
          </div>
        </div>
      `;
    }).join('');

    timeline.innerHTML = items;
  }

  // ==================== BACKEND SERVERS MANAGEMENT ====================
  async function fetchServersList() {
    try {
      const res = await fetch('/api/servers');
      if (!res.ok) return;
      const data = await res.json();
      const tbody = document.getElementById('servers-table-body');
      if (!tbody) return;

      if (!data.servers || !data.servers.length) {
        tbody.innerHTML = '<tr><td colspan="11" class="empty-state">No backend servers registered.</td></tr>';
        return;
      }

      tbody.innerHTML = data.servers.map(s => `
        <tr>
          <td>
            <strong>${s.name}</strong><br>
            <span class="mono" style="font-size: 11px; color: var(--text-muted);">${s.id}</span>
          </td>
          <td><span class="mono">${s.url}</span></td>
          <td>${getStatusBadge(s.status)}</td>
          <td>${getCircuitBadge(s.circuit_state)}</td>
          <td><span class="badge badge-neutral">Weight: ${s.weight}</span></td>
          <td><strong>${s.active_connections || 0}</strong> in-flight</td>
          <td>
            <span style="color: ${s.consecutive_failures > 0 ? 'var(--color-danger)' : 'var(--text-muted)'}; font-weight: 600;">
              ${s.consecutive_failures || 0}
            </span>
          </td>
          <td>${s.total_requests}</td>
          <td>${s.last_response_time_ms || 0} ms</td>
          <td><span style="font-size: 11px; color: var(--text-muted);">${s.last_health_check || 'Pending'}</span></td>
          <td>
            <div style="display: flex; gap: 4px;">
              <button class="btn btn-secondary btn-sm" onclick="toggleServer('${s.id}')" title="${s.is_enabled ? 'Disable' : 'Enable'}">
                ${s.is_enabled ? 'Disable' : 'Enable'}
              </button>
              <button class="btn btn-warning btn-sm" onclick="manualTripCircuit('${s.id}')" title="Force Open Circuit">
                Trip
              </button>
              <button class="btn btn-success btn-sm" onclick="manualResetCircuit('${s.id}')" title="Reset Circuit">
                Reset
              </button>
              <button class="btn btn-danger btn-sm" onclick="deleteServer('${s.id}')" title="Delete">
                &times;
              </button>
            </div>
          </td>
        </tr>
      `).join('');
    } catch (err) {
      console.error(err);
    }
  }

  // Server Actions
  window.toggleServer = async function(serverId) {
    try {
      const res = await fetch(`/api/servers/${serverId}/toggle`, { method: 'POST' });
      const data = await res.json();
      showToast(data.message, 'info');
      fetchServersList();
    } catch (err) {
      showToast('Error toggling server', 'error');
    }
  };

  window.manualResetCircuit = async function(serverId) {
    try {
      const res = await fetch(`/api/servers/${serverId}/circuit/reset`, { method: 'POST' });
      const data = await res.json();
      showToast(data.message, 'success');
      fetchServersList();
    } catch (err) {
      showToast('Error resetting circuit breaker', 'error');
    }
  };

  window.manualTripCircuit = async function(serverId) {
    try {
      const res = await fetch(`/api/servers/${serverId}/circuit/trip`, { method: 'POST' });
      const data = await res.json();
      showToast(data.message, 'error');
      fetchServersList();
    } catch (err) {
      showToast('Error tripping circuit breaker', 'error');
    }
  };

  window.deleteServer = async function(serverId) {
    if (!confirm(`Are you sure you want to remove server ${serverId}?`)) return;
    try {
      const res = await fetch(`/api/servers/${serverId}`, { method: 'DELETE' });
      const data = await res.json();
      showToast(data.message, 'info');
      fetchServersList();
    } catch (err) {
      showToast('Error deleting server', 'error');
    }
  };

  // Add Server Modal
  const modalServer = document.getElementById('modal-server');
  const btnOpenAddServer = document.getElementById('btn-open-add-server');
  const btnCloseModal = document.getElementById('btn-close-modal');
  const btnCancelModal = document.getElementById('btn-cancel-modal');
  const btnSaveServer = document.getElementById('btn-save-server');

  if (btnOpenAddServer) {
    btnOpenAddServer.addEventListener('click', () => {
      document.getElementById('server-form').reset();
      document.getElementById('modal-server-title').textContent = 'Register Backend Server';
      document.getElementById('form-is-edit').value = '0';
      document.getElementById('form-server-id').disabled = false;
      modalServer.classList.add('active');
    });
  }

  [btnCloseModal, btnCancelModal].forEach(b => {
    if (b) b.addEventListener('click', () => modalServer.classList.remove('active'));
  });

  if (btnSaveServer) {
    btnSaveServer.addEventListener('click', async (e) => {
      e.preventDefault();
      const sId = document.getElementById('form-server-id').value.trim();
      const sName = document.getElementById('form-server-name').value.trim();
      const sUrl = document.getElementById('form-server-url').value.trim();
      const sWeight = parseInt(document.getElementById('form-server-weight').value) || 1;

      if (!sId || !sName || !sUrl) {
        showToast('Please provide ID, Name, and URL', 'error');
        return;
      }

      try {
        const res = await fetch('/api/servers', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: sId, name: sName, url: sUrl, weight: sWeight })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.message, 'success');
          modalServer.classList.remove('active');
          fetchServersList();
        } else {
          showToast(data.error || 'Failed to save server', 'error');
        }
      } catch (err) {
        showToast('Network error saving server', 'error');
      }
    });
  }

  // ==================== LOAD BALANCING ALGORITHMS ====================
  const selectActiveAlgo = document.getElementById('select-active-algo');
  const btnSaveAlgo = document.getElementById('btn-save-algo');
  const algoAppliedMsg = document.getElementById('algo-applied-msg');

  async function loadAlgorithmSettings() {
    try {
      const res = await fetch('/api/algorithms');
      if (!res.ok) return;
      const data = await res.json();
      if (selectActiveAlgo) selectActiveAlgo.value = data.active;
      headerAlgoName.textContent = data.active;
    } catch (err) {
      console.error(err);
    }
  }

  if (btnSaveAlgo) {
    btnSaveAlgo.addEventListener('click', async () => {
      const selected = selectActiveAlgo.value;
      try {
        const res = await fetch('/api/algorithm', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ algorithm: selected })
        });
        const data = await res.json();
        if (res.ok) {
          headerAlgoName.textContent = data.algorithm;
          algoAppliedMsg.style.display = 'inline';
          showToast(`Algorithm changed to ${data.algorithm}`, 'success');
          setTimeout(() => { algoAppliedMsg.style.display = 'none'; }, 3000);
        } else {
          showToast(data.error, 'error');
        }
      } catch (err) {
        showToast('Error updating algorithm', 'error');
      }
    });
  }

  // ==================== CIRCUIT BREAKER VIEW ====================
  async function fetchCircuitBreakerView() {
    try {
      const [resServers, resTrans] = await Promise.all([
        fetch('/api/servers'),
        fetch('/api/logs/transitions?limit=20')
      ]);

      if (!resServers.ok || !resTrans.ok) return;
      const serversData = await resServers.json();
      const transData = await resTrans.json();

      // Render Circuit Server Cards
      const container = document.getElementById('circuit-server-cards-container');
      if (container) {
        container.innerHTML = serversData.servers.map(s => {
          const info = s.circuit_info || {};
          const isClosed = s.circuit_state === 'CLOSED';
          const isOpen = s.circuit_state === 'OPEN';
          const isHalfOpen = s.circuit_state === 'HALF-OPEN';

          return `
            <div class="panel" style="margin-bottom: 0;">
              <div class="panel-header">
                <div>
                  <span class="panel-title">${s.name}</span>
                  <span class="mono" style="font-size: 11px; color: var(--text-muted);">${s.url}</span>
                </div>
                ${getCircuitBadge(s.circuit_state)}
              </div>
              <div class="panel-body">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 14px; font-size: 12px;">
                  <div>
                    <span style="color: var(--text-muted);">Consecutive Failures:</span><br>
                    <strong style="color: ${s.consecutive_failures >= 3 ? 'var(--color-danger)' : 'var(--text-primary)'}; font-size: 14px;">
                      ${s.consecutive_failures} / ${info.failure_threshold || 3}
                    </strong>
                  </div>
                  <div>
                    <span style="color: var(--text-muted);">Recovery Successes:</span><br>
                    <strong style="color: var(--color-healthy); font-size: 14px;">
                      ${s.consecutive_successes} / ${info.recovery_threshold || 2}
                    </strong>
                  </div>
                  <div>
                    <span style="color: var(--text-muted);">Time in Current State:</span><br>
                    <strong>${info.time_in_state_seconds || 0}s</strong>
                  </div>
                  <div>
                    <span style="color: var(--text-muted);">Time Until Probe:</span><br>
                    <strong style="color: var(--color-warning);">${info.time_until_probe_seconds || 0}s</strong>
                  </div>
                </div>

                <div style="display: flex; gap: 8px;">
                  <button class="btn btn-warning btn-sm" onclick="manualTripCircuit('${s.id}')">Manual Trip (OPEN)</button>
                  <button class="btn btn-success btn-sm" onclick="manualResetCircuit('${s.id}')">Manual Reset (CLOSED)</button>
                </div>
              </div>
            </div>
          `;
        }).join('');
      }

      // Render Circuit Transitions Table
      const transTbody = document.getElementById('circuit-transitions-tbody');
      if (transTbody) {
        if (!transData.transitions || !transData.transitions.length) {
          transTbody.innerHTML = '<tr><td colspan="6" class="empty-state">No circuit transitions recorded.</td></tr>';
        } else {
          transTbody.innerHTML = transData.transitions.map(t => `
            <tr>
              <td><span class="mono">${t.timestamp}</span></td>
              <td><strong>${t.server_name || t.server_id}</strong></td>
              <td>${getCircuitBadge(t.from_state)}</td>
              <td>${getCircuitBadge(t.to_state)}</td>
              <td>${t.failure_count}</td>
              <td style="color: var(--text-secondary);">${t.reason}</td>
            </tr>
          `).join('');
        }
      }
    } catch (err) {
      console.error(err);
    }
  }

  // ==================== RECOVERY INTELLIGENCE ====================
  async function fetchRecoveryIntelligence() {
    try {
      const res = await fetch('/api/metrics/recovery-intelligence');
      if (!res.ok) return;
      const data = await res.json();

      document.getElementById('intel-det-time').textContent = `${data.avg_detection_latency_ms || 0} ms`;
      document.getElementById('intel-rec-time').textContent = `${data.avg_recovery_duration_ms || 0} ms`;
      document.getElementById('intel-continuity-text').textContent = data.failover_continuity ? '100%' : 'Degraded';
      document.getElementById('intel-continuity-badge').textContent = data.failover_continuity ? 'Maintained' : 'Disrupted';
      document.getElementById('intel-continuity-badge').className = `badge ${data.failover_continuity ? 'badge-healthy' : 'badge-danger'}`;
      document.getElementById('intel-incidents-count').textContent = data.total_faults_tracked || 0;
      document.getElementById('intel-recovered-count').textContent = data.recovered_faults_count || 0;

      // Recorded Faults Table
      const tbody = document.getElementById('intel-faults-tbody');
      if (tbody) {
        if (!data.fault_events || !data.fault_events.length) {
          tbody.innerHTML = '<tr><td colspan="9" class="empty-state">No fault events recorded. Inject a fault in the Fault-Injection Lab to measure detection latency and recovery time.</td></tr>';
        } else {
          tbody.innerHTML = data.fault_events.map(f => `
            <tr>
              <td><span class="mono">${f.event_id}</span></td>
              <td><strong>${f.server_id}</strong></td>
              <td><span class="badge badge-warning">${f.fault_type}</span></td>
              <td><span class="mono">${f.injected_at}</span></td>
              <td><span class="mono">${f.detected_at || '<em style="color:var(--text-muted);">Detecting...</em>'}</span></td>
              <td><strong>${f.detection_latency_ms ? f.detection_latency_ms + ' ms' : '-'}</strong></td>
              <td><span class="mono">${f.recovered_at || '<em style="color:var(--text-muted);">Probing...</em>'}</span></td>
              <td><strong>${f.recovery_duration_ms ? f.recovery_duration_ms + ' ms' : '-'}</strong></td>
              <td>${getStatusBadge(f.status)}</td>
            </tr>
          `).join('');
        }
      }
    } catch (err) {
      console.error(err);
    }
  }

  const btnRefreshIntel = document.getElementById('btn-refresh-intelligence');
  if (btnRefreshIntel) {
    btnRefreshIntel.addEventListener('click', () => {
      fetchRecoveryIntelligence();
      showToast('Recovery intelligence metrics refreshed', 'info');
    });
  }

  // ==================== FAULT-INJECTION LAB ====================
  window.injectFault = async function(serverId, faultType, paramVal) {
    try {
      const res = await fetch('/api/experiment/fault', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ server_id: serverId, fault_type: faultType, param_val: paramVal })
      });
      const data = await res.json();
      if (res.ok) {
        showToast(data.message, faultType === 'RECOVER' ? 'success' : 'warning');
        // Refresh overview and servers after short delay
        setTimeout(() => {
          fetchOverviewData();
          fetchServersList();
        }, 500);
      } else {
        showToast(data.error || 'Failed to inject fault', 'error');
      }
    } catch (err) {
      showToast('Error communicating with fault injection API', 'error');
    }
  };

  // Cluster controls
  const btnClusterStartAll = document.getElementById('btn-cluster-start-all');
  const btnClusterStopAll = document.getElementById('btn-cluster-stop-all');

  if (btnClusterStartAll) {
    btnClusterStartAll.addEventListener('click', async () => {
      const res = await fetch('/api/experiment/cluster/start', { method: 'POST' });
      const data = await res.json();
      showToast(data.message, 'success');
      fetchServersList();
    });
  }

  if (btnClusterStopAll) {
    btnClusterStopAll.addEventListener('click', async () => {
      const res = await fetch('/api/experiment/cluster/stop', { method: 'POST' });
      const data = await res.json();
      showToast(data.message, 'error');
      fetchServersList();
    });
  }

  // Synthetic Workload Generator
  const btnStartWorkload = document.getElementById('btn-start-workload');
  const btnStopWorkload = document.getElementById('btn-stop-workload');
  const workloadProgressArea = document.getElementById('workload-progress-area');
  const workloadProgText = document.getElementById('workload-prog-text');
  const workloadSuccessText = document.getElementById('workload-success-text');
  const workloadFailText = document.getElementById('workload-fail-text');
  const workloadProgBar = document.getElementById('workload-prog-bar');
  const workloadStatusBadge = document.getElementById('workload-status-badge');
  const workloadDistPills = document.getElementById('workload-dist-pills');

  if (btnStartWorkload) {
    btnStartWorkload.addEventListener('click', async () => {
      const total = parseInt(document.getElementById('workload-req-count').value) || 50;
      const concurrency = parseInt(document.getElementById('workload-concurrency').value) || 2;
      const delayMs = parseInt(document.getElementById('workload-delay-ms').value) || 30;

      try {
        const res = await fetch('/api/experiment/workload/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ total_requests: total, concurrency, delay_ms: delayMs })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(`Started workload with ${total} requests`, 'info');
          workloadProgressArea.style.display = 'block';
          workloadStatusBadge.textContent = 'Running';
          workloadStatusBadge.className = 'badge badge-warning';
          startWorkloadPolling();
        } else {
          showToast(data.error || 'Failed to start workload', 'error');
        }
      } catch (err) {
        showToast('Error starting workload', 'error');
      }
    });
  }

  if (btnStopWorkload) {
    btnStopWorkload.addEventListener('click', async () => {
      try {
        const res = await fetch('/api/experiment/workload/stop', { method: 'POST' });
        const data = await res.json();
        showToast(data.message, 'warning');
        workloadStatusBadge.textContent = 'Stopped';
        workloadStatusBadge.className = 'badge badge-danger';
        clearInterval(workloadTimer);
      } catch (err) {
        showToast('Error stopping workload', 'error');
      }
    });
  }

  function startWorkloadPolling() {
    clearInterval(workloadTimer);
    workloadTimer = setInterval(async () => {
      try {
        const res = await fetch('/api/experiment/workload/status');
        if (!res.ok) return;
        const data = await res.json();
        const job = data.workload;
        if (!job) return;

        const pct = job.total_requests > 0 ? Math.min(100, Math.round((job.completed / job.total_requests) * 100)) : 0;
        workloadProgBar.style.width = `${pct}%`;
        workloadProgText.textContent = `${job.completed} / ${job.total_requests} (${pct}%)`;
        workloadSuccessText.textContent = job.successful;
        workloadFailText.textContent = job.failed;

        // Render per-backend distribution pills
        if (job.distribution) {
          workloadDistPills.innerHTML = Object.entries(job.distribution).map(([b, cnt]) => `
            <span class="badge badge-neutral">${b}: <strong>${cnt}</strong></span>
          `).join('');
        }

        if (!job.is_running) {
          clearInterval(workloadTimer);
          workloadStatusBadge.textContent = job.status || 'Completed';
          workloadStatusBadge.className = job.status === 'COMPLETED' ? 'badge badge-healthy' : 'badge badge-danger';
          showToast(`Workload finished: ${job.successful} success, ${job.failed} failed`, job.successful > 0 ? 'success' : 'warning');
          // Refresh overview metrics
          fetchOverviewData();
        }
      } catch (err) {
        console.error(err);
      }
    }, 600);
  }

  // ==================== EVENT LOGS VIEW ====================
  async function fetchRequestLogs() {
    const backend = document.getElementById('log-filter-backend')?.value || '';
    const status = document.getElementById('log-filter-status')?.value || '';

    try {
      const res = await fetch(`/api/logs/requests?backend=${encodeURIComponent(backend)}&status=${encodeURIComponent(status)}&limit=100`);
      if (!res.ok) return;
      const data = await res.json();
      const tbody = document.getElementById('logs-request-tbody');
      if (!tbody) return;

      if (!data.logs || !data.logs.length) {
        tbody.innerHTML = '<tr><td colspan="10" class="empty-state">No matching request logs found.</td></tr>';
        return;
      }

      tbody.innerHTML = data.logs.map(log => `
        <tr>
          <td><span class="mono">${log.timestamp}</span></td>
          <td><span class="mono" style="font-size: 11px;">${log.request_id}</span></td>
          <td><span class="badge badge-neutral">${log.method}</span></td>
          <td><span class="mono">${log.path}</span></td>
          <td><strong>${log.selected_backend_id || '<em style="color:var(--color-danger);">None (503)</em>'}</strong></td>
          <td><span class="badge badge-info">${log.algorithm_used}</span></td>
          <td><span class="mono">${log.status_code || 500}</span></td>
          <td>${log.response_time_ms} ms</td>
          <td>${log.is_success ? '<span class="badge badge-healthy">SUCCESS</span>' : '<span class="badge badge-danger">FAILED</span>'}</td>
          <td><span style="font-size: 11px; color: var(--text-muted);">${log.error_message || '-'}</span></td>
        </tr>
      `).join('');
    } catch (err) {
      console.error(err);
    }
  }

  const btnApplyLogFilter = document.getElementById('btn-apply-log-filter');
  if (btnApplyLogFilter) {
    btnApplyLogFilter.addEventListener('click', () => {
      fetchRequestLogs();
      showToast('Filters applied', 'info');
    });
  }

  // ==================== SETTINGS VIEW ====================
  async function fetchSettings() {
    try {
      const res = await fetch('/api/settings');
      if (!res.ok) return;
      const data = await res.json();
      const s = data.settings || {};

      if (document.getElementById('cfg-health-interval')) {
        document.getElementById('cfg-health-interval').value = s.health_check_interval || 3.0;
        document.getElementById('cfg-health-timeout').value = s.health_check_timeout || 1.5;
        document.getElementById('cfg-request-timeout').value = s.request_timeout || 3.0;
        document.getElementById('cfg-failure-threshold').value = s.failure_threshold || 3;
        document.getElementById('cfg-recovery-threshold').value = s.recovery_threshold || 2;
        document.getElementById('cfg-recovery-delay').value = s.recovery_delay || 5.0;
      }
    } catch (err) {
      console.error(err);
    }
  }

  const btnSaveSettings = document.getElementById('btn-save-settings');
  if (btnSaveSettings) {
    btnSaveSettings.addEventListener('click', async (e) => {
      e.preventDefault();
      const payload = {
        health_check_interval: parseFloat(document.getElementById('cfg-health-interval').value),
        health_check_timeout: parseFloat(document.getElementById('cfg-health-timeout').value),
        request_timeout: parseFloat(document.getElementById('cfg-request-timeout').value),
        failure_threshold: parseInt(document.getElementById('cfg-failure-threshold').value),
        recovery_threshold: parseInt(document.getElementById('cfg-recovery-threshold').value),
        recovery_delay: parseFloat(document.getElementById('cfg-recovery-delay').value)
      };

      try {
        const res = await fetch('/api/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.message, 'success');
        } else {
          showToast(data.error || 'Failed to save settings', 'error');
        }
      } catch (err) {
        showToast('Error saving settings', 'error');
      }
    });
  }

  // ==================== QUICK ACTION: SEND TEST REQUEST ====================
  if (btnQuickTraffic) {
    btnQuickTraffic.addEventListener('click', async () => {
      const startTime = performance.now();
      try {
        const res = await fetch('/proxy/', { method: 'GET' });
        const latency = Math.round(performance.now() - startTime);
        const backend = res.headers.get('X-Handled-By') || 'unknown';
        const algo = res.headers.get('X-Load-Balancer-Algo') || '';

        if (res.ok) {
          showToast(`[${res.status} OK] Dispatched via ${algo} to ${backend} in ${latency}ms`, 'success');
        } else {
          showToast(`[HTTP ${res.status}] ${backend || 'No backend'}: ${res.statusText}`, 'error');
        }
        // Immediate overview refresh
        fetchOverviewData();
      } catch (err) {
        showToast('Proxy request failed: connection error', 'error');
      }
    });
  }

  if (btnManualRefresh) {
    btnManualRefresh.addEventListener('click', () => {
      refreshCurrentView();
      showToast('Console data refreshed', 'info');
    });
  }

  // Helper Badge Functions
  function getStatusBadge(status) {
    if (status === 'HEALTHY' || status === 'UP' || status === 'RESOLVED') {
      return '<span class="badge badge-healthy"><span class="dot dot-healthy"></span> Healthy</span>';
    } else if (status === 'DEGRADED' || status === 'RECOVERING' || status === 'SLOW') {
      return '<span class="badge badge-warning"><span class="dot dot-warning"></span> Degraded</span>';
    } else {
      return '<span class="badge badge-danger"><span class="dot dot-danger"></span> Unhealthy</span>';
    }
  }

  function getCircuitBadge(circuitState) {
    if (circuitState === 'CLOSED') {
      return '<span class="badge badge-healthy">CLOSED</span>';
    } else if (circuitState === 'OPEN') {
      return '<span class="badge badge-danger">OPEN</span>';
    } else if (circuitState === 'HALF-OPEN') {
      return '<span class="badge badge-warning">HALF-OPEN</span>';
    }
    return `<span class="badge badge-neutral">${circuitState || 'UNKNOWN'}</span>`;
  }

  // View Refresh Controller
  function refreshCurrentView() {
    if (activeView === 'overview') {
      fetchOverviewData();
    } else if (activeView === 'servers') {
      fetchServersList();
    } else if (activeView === 'algorithms') {
      loadAlgorithmSettings();
    } else if (activeView === 'circuit-breaker') {
      fetchCircuitBreakerView();
    } else if (activeView === 'recovery-intelligence') {
      fetchRecoveryIntelligence();
    } else if (activeView === 'fault-lab') {
      fetchServersList();
    } else if (activeView === 'logs') {
      fetchRequestLogs();
    } else if (activeView === 'settings') {
      fetchSettings();
    }
  }

  // Initial Load
  fetchOverviewData();
  loadAlgorithmSettings();

  // Background Periodic Refresh (Every 3.0s)
  pollTimer = setInterval(() => {
    if (activeView === 'overview') fetchOverviewData();
    else if (activeView === 'servers') fetchServersList();
    else if (activeView === 'circuit-breaker') fetchCircuitBreakerView();
  }, 3000);
});
