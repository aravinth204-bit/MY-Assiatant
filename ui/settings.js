let scannedCandidates = [];

document.addEventListener('DOMContentLoaded', () => {
  // Start polling system monitor stats every 2 seconds
  setInterval(refreshMonitorStats, 2000);
  refreshMonitorStats();
  loadTrackedSites();
  loadConfigSettings();
  
  // Poll pomodoro timer every second
  setInterval(refreshPomodoro, 1000);
});

function switchTab(tabId) {
  document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
  
  const targetPanel = document.getElementById(`tab-${tabId}`);
  if (targetPanel) {
    targetPanel.classList.add('active');
  }
  
  event.currentTarget.classList.add('active');
}

function refreshMonitorStats() {
  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.get_system_stats().then(stats => {
      document.getElementById('cpu-val').innerText = `${stats.cpu_percent}%`;
      document.getElementById('cpu-fill').style.width = `${stats.cpu_percent}%`;

      document.getElementById('ram-val').innerText = `${stats.ram_percent}%`;
      document.getElementById('ram-sub').innerText = `${stats.ram_used_gb} / ${stats.ram_total_gb} GB`;
      document.getElementById('ram-fill').style.width = `${stats.ram_percent}%`;

      document.getElementById('disk-val').innerText = `${stats.disk_percent}%`;
      document.getElementById('disk-sub').innerText = `${stats.disk_free_gb} GB free`;
      document.getElementById('disk-fill').style.width = `${stats.disk_percent}%`;

      document.getElementById('battery-val').innerText = `${stats.battery_percent}%`;
      document.getElementById('battery-sub').innerText = stats.is_plugged ? "🔌 Plugged in" : "🔋 Discharging";
    }).catch(err => console.log(err));

    window.pywebview.api.get_top_processes(5).then(procs => {
      const tbody = document.getElementById('process-table-body');
      tbody.innerHTML = '';
      procs.forEach(p => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${p.pid}</td>
          <td><strong>${escapeHtml(p.name)}</strong></td>
          <td>${p.cpu_percent}%</td>
          <td>${p.ram_mb} MB</td>
          <td><button class="danger-btn" onclick="terminateProc(${p.pid}, '${escapeHtml(p.name)}')">End Process</button></td>
        `;
        tbody.appendChild(tr);
      });
    }).catch(err => console.log(err));
  }
}

function terminateProc(pid, name) {
  if (confirm(`Are you sure you want to terminate process "${name}" (PID: ${pid})?`)) {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.terminate_process(pid).then(success => {
        if (success) {
          alert(`Process ${name} ended successfully.`);
          refreshMonitorStats();
        } else {
          alert(`Failed to terminate process ${name}. Access denied or process exited.`);
        }
      });
    }
  }
}

function runCleanerScan() {
  const container = document.getElementById('scan-results-list');
  container.innerHTML = '<p class="loading-text">Scanning temporary files, installer downloads, and duplicates...</p>';

  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.scan_cleaner().then(results => {
      scannedCandidates = results || [];
      renderScanResults();
    }).catch(err => {
      container.innerHTML = '<p class="empty-state">Error performing scan.</p>';
    });
  }
}

function renderScanResults() {
  const container = document.getElementById('scan-results-list');
  const badge = document.getElementById('scan-summary-badge');
  const cleanBtn = document.getElementById('clean-btn');

  container.innerHTML = '';

  if (scannedCandidates.length === 0) {
    container.innerHTML = '<p class="empty-state">No junk files found! Your disk is clean.</p>';
    badge.innerText = '0 Files Found (0 MB)';
    cleanBtn.disabled = true;
    return;
  }

  let totalBytes = 0;
  scannedCandidates.forEach((item, index) => {
    totalBytes += item.size_bytes;
    const mb = (item.size_bytes / (1024 * 1024)).toFixed(1);
    const div = document.createElement('div');
    div.className = 'scan-item';
    div.innerHTML = `
      <input type="checkbox" id="scan-chk-${index}" checked value="${escapeHtml(item.path)}">
      <div class="scan-item-info">
        <div><strong>[${escapeHtml(item.category)}]</strong> ${mb} MB — ${escapeHtml(item.reason)}</div>
        <div class="scan-item-path">${escapeHtml(item.path)}</div>
      </div>
    `;
    container.appendChild(div);
  });

  const totalMb = (totalBytes / (1024 * 1024)).toFixed(1);
  badge.innerText = `${scannedCandidates.length} Files Found (${totalMb} MB)`;
  cleanBtn.disabled = false;
}

function cleanSelectedFiles() {
  const selectedPaths = [];
  scannedCandidates.forEach((item, index) => {
    const chk = document.getElementById(`scan-chk-${index}`);
    if (chk && chk.checked) {
      selectedPaths.push(item.path);
    }
  });

  if (selectedPaths.length === 0) {
    alert("Please select at least one file to move to Recycle Bin.");
    return;
  }

  if (confirm(`Move ${selectedPaths.length} selected files safely to Windows Recycle Bin?`)) {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.perform_cleanup(selectedPaths).then(res => {
        alert(`Cleanup complete! ${res.success_count} files moved to Recycle Bin (${res.freed_mb} MB freed).`);
        runCleanerScan();
      });
    }
  }
}

function loadTrackedSites() {
  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.get_config().then(cfg => {
      const tbody = document.getElementById('sites-table-body');
      tbody.innerHTML = '';
      const sites = cfg.tracked_websites || [];
      sites.forEach(s => {
        const usedMins = (s.used_seconds / 60).toFixed(1);
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${escapeHtml(s.domain)}</strong></td>
          <td>${s.limit_minutes} mins</td>
          <td>${usedMins} mins</td>
          <td><button class="danger-btn" onclick="removeTrackedSite('${escapeHtml(s.domain)}')">Remove</button></td>
        `;
        tbody.appendChild(tr);
      });
    });
  }
}

function addTrackedSite() {
  const domainInput = document.getElementById('site-domain');
  const limitInput = document.getElementById('site-limit');
  const domain = domainInput.value.trim();
  const limit = parseInt(limitInput.value);

  if (!domain || isNaN(limit) || limit <= 0) {
    alert("Please enter a valid website domain and time limit in minutes.");
    return;
  }

  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.get_config().then(cfg => {
      cfg.tracked_websites = cfg.tracked_websites || [];
      cfg.tracked_websites.push({ domain: domain, limit_minutes: limit, used_seconds: 0 });
      window.pywebview.api.save_config(cfg).then(() => {
        domainInput.value = '';
        limitInput.value = '';
        loadTrackedSites();
      });
    });
  }
}

function removeTrackedSite(domain) {
  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.get_config().then(cfg => {
      cfg.tracked_websites = (cfg.tracked_websites || []).filter(s => s.domain.toLowerCase() !== domain.toLowerCase());
      window.pywebview.api.save_config(cfg).then(() => {
        loadTrackedSites();
      });
    });
  }
}

function startPomodoro() {
  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.start_pomodoro(25);
  }
}

function stopPomodoro() {
  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.stop_pomodoro();
  }
}

function refreshPomodoro() {
  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.get_pomodoro_status().then(status => {
      const display = document.getElementById('pomodoro-timer');
      const statusText = document.getElementById('pomodoro-status');
      
      if (!status.active) {
        display.innerText = "25:00";
        statusText.innerText = "Ready for a focus session";
      } else {
        const mins = Math.floor(status.remaining_seconds / 60).toString().padStart(2, '0');
        const secs = (status.remaining_seconds % 60).toString().padStart(2, '0');
        display.innerText = `${mins}:${secs}`;
        statusText.innerText = status.mode === 'work' ? "🔥 Focus Sprint in Progress" : "☕ Break Time!";
      }
    });
  }
}

function loadConfigSettings() {
  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.get_config().then(cfg => {
      document.getElementById('cfg-char-name').value = cfg.character_name || "Aravi";
      document.getElementById('cfg-storage-threshold').value = cfg.storage_threshold_pct || 90;
      document.getElementById('cfg-startup').checked = cfg.start_with_windows || false;
    });
  }
}

function saveGeneralSettings() {
  const name = document.getElementById('cfg-char-name').value.trim();
  const threshold = parseInt(document.getElementById('cfg-storage-threshold').value);
  const startup = document.getElementById('cfg-startup').checked;

  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.get_config().then(cfg => {
      cfg.character_name = name;
      cfg.storage_threshold_pct = threshold;
      cfg.start_with_windows = startup;
      window.pywebview.api.save_config(cfg).then(() => {
        alert("Preferences saved!");
      });
    });
  }
}

function escapeHtml(str) {
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
