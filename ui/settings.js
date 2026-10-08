const SITE_DEFAULTS = [
  { domain: 'youtube.com', inputId: 'youtube-limit', fallback: 30 },
  { domain: 'instagram.com', inputId: 'instagram-limit', fallback: 20 }
];

let activeFileSearchId = null;
let fileSearchPollTimer = null;
let fileSearchPollPending = false;
let activeFileSearchOnComplete = null;
let geminiHistory = [];
let localHistory = [];
let webSearchHistory = [];
let opencodeHistory = [];
let activityRefreshTimer = null;
let waterReminderPendingShown = false;

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('limits-form').addEventListener('submit', saveLimits);
  document.getElementById('water-reminder-form').addEventListener('submit', saveWaterReminderInterval);
  document.getElementById('water-reminder-yes').addEventListener('click', () => respondToWaterReminder('yes'));
  document.getElementById('water-reminder-no').addEventListener('click', () => respondToWaterReminder('no'));
  document.getElementById('file-search-form').addEventListener('submit', searchFiles);
  document.getElementById('chat-form').addEventListener('submit', handleChatMessage);
  document.getElementById('chat-agent').addEventListener('change', updateChatAgentBadge);
  document.getElementById('file-search-cancel').addEventListener('click', cancelFileSearch);
  document.getElementById('observation-toggle').addEventListener('click', toggleObservation);
  document.querySelectorAll('[data-page]').forEach(link => {
    link.addEventListener('click', () => showPage(link.dataset.page));
  });
  window.addEventListener('hashchange', () => {
    showPage(window.location.hash.slice(1));
  });
  showPage(window.location.hash.slice(1) || 'dashboard-panel');
  updateChatAgentBadge();
  loadLimits();
  refreshWaterReminderStatus();
  setInterval(refreshWaterReminderStatus, 5000);
  loadObservationStatus();
  loadActivityHistory();
  loadDashboardHistory();
});

function showPage(pageId) {
  const panels = document.querySelectorAll('.page-panel');
  if (!Array.from(panels).some(panel => panel.id === pageId)) {
    pageId = 'dashboard-panel';
  }
  panels.forEach(panel => {
    panel.hidden = panel.id !== pageId;
  });
  document.querySelectorAll('.nav-btn').forEach(link => {
    link.classList.toggle('active', link.dataset.page === pageId);
  });
  if (pageId === 'dashboard-panel' || pageId === 'activity-panel') {
    loadActivityHistory();
  }
  if (pageId === 'dashboard-panel') loadDashboardHistory();
}

async function searchFiles(event, onComplete = null) {
  event.preventDefault();
  const input = document.getElementById('file-name');
  const status = document.getElementById('file-search-status');
  const progress = document.getElementById('file-search-progress');
  const results = document.getElementById('file-search-results');
  const submit = document.getElementById('file-search-submit');
  const cancel = document.getElementById('file-search-cancel');
  const query = input.value.trim();

  if (!window.pywebview || !window.pywebview.api) {
    status.textContent = 'ARAVI is not available.';
    if (onComplete) onComplete(new Error('ARAVI is not available.'));
    return;
  }
  if (!query) {
    status.textContent = 'Enter a file name to search for.';
    if (onComplete) onComplete(new Error('Enter a file name to search for.'));
    return;
  }

  if (activeFileSearchId) {
    if (onComplete) onComplete(new Error('A file search is already running.'));
    return;
  }

  status.textContent = 'Starting search on local drives...';
  progress.textContent = 'You can cancel the search at any time.';
  results.replaceChildren();
  submit.disabled = true;
  cancel.hidden = false;
  activeFileSearchOnComplete = onComplete;
  try {
    activeFileSearchId = await window.pywebview.api.start_file_search(query);
    fileSearchPollTimer = setInterval(pollFileSearch, 500);
  } catch (error) {
    const callback = activeFileSearchOnComplete;
    finishFileSearch();
    status.textContent = `Could not start file search: ${error.message || error}`;
    if (callback) callback(error);
  }
}

async function pollFileSearch() {
  if (!activeFileSearchId || fileSearchPollPending) return;
  const status = document.getElementById('file-search-status');
  const progress = document.getElementById('file-search-progress');
  fileSearchPollPending = true;
  try {
    const response = await window.pywebview.api.get_file_search_status(activeFileSearchId);
    progress.textContent = response.current_path
      ? `${response.scanned_directories.toLocaleString()} folders, ${
        response.scanned_entries.toLocaleString()
      } items checked; ${response.match_count} matches so far.\n${response.current_path}`
      : `${response.scanned_directories.toLocaleString()} folders and ${
        response.scanned_entries.toLocaleString()
      } items checked; ${response.match_count} matches so far.`;

    if (response.status === 'running') return;
    const onComplete = activeFileSearchOnComplete;
    finishFileSearch();
    if (response.status === 'failed') {
      status.textContent = `File search failed: ${response.error}`;
      if (onComplete) onComplete(new Error(response.error));
      return;
    }
    showFileSearchResults(response, status);
    if (!response.cancelled) await recordDashboardActivity('file_search');
    if (onComplete) onComplete(null, response);
  } catch (error) {
    const callback = activeFileSearchOnComplete;
    finishFileSearch();
    status.textContent = `Could not read file search status: ${error.message || error}`;
    if (callback) callback(error);
  } finally {
    fileSearchPollPending = false;
  }
}

async function cancelFileSearch() {
  if (!activeFileSearchId) return;
  const status = document.getElementById('file-search-status');
  try {
    await window.pywebview.api.cancel_file_search(activeFileSearchId);
    status.textContent = 'Stopping the file search...';
  } catch (error) {
    status.textContent = `Could not cancel file search: ${error.message || error}`;
  }
}

function showFileSearchResults(response, status) {
  const progress = document.getElementById('file-search-progress');
  const results = document.getElementById('file-search-results');
  response.matches.forEach(match => {
      const item = document.createElement('li');
      const name = document.createElement('strong');
      const path = document.createElement('span');
      name.textContent = match.name;
      path.textContent = match.path;
      item.append(name, path);
      results.append(item);
  });

  const found = response.matches.length;
  const countMessage = found === 1 ? '1 file found.' : `${found} files found.`;
  const skippedMessage = response.skipped_directories
    ? ` ${response.skipped_directories} folders could not be accessed.`
    : '';
  const skippedItemsMessage = response.skipped_items
    ? ` ${response.skipped_items} ${
      response.skipped_items === 1 ? 'item' : 'items'
    } could not be checked.`
    : '';
  const limitMessage = response.truncated
    ? ' Showing up to 50 matches; try a more specific name for more precise results.'
    : '';
  const cancelMessage = response.cancelled ? ' Search cancelled.' : '';
  status.textContent = `${countMessage}${skippedMessage}${skippedItemsMessage}${limitMessage}${cancelMessage}`;
  progress.textContent = `${response.scanned_directories.toLocaleString()} folders and ${
    response.scanned_entries.toLocaleString()
  } items checked.`;
}

function finishFileSearch() {
  activeFileSearchId = null;
  fileSearchPollPending = false;
  activeFileSearchOnComplete = null;
  if (fileSearchPollTimer !== null) {
    clearInterval(fileSearchPollTimer);
    fileSearchPollTimer = null;
  }
  document.getElementById('file-search-submit').disabled = false;
  document.getElementById('file-search-cancel').hidden = true;
}

async function handleChatMessage(event) {
  event.preventDefault();
  const input = document.getElementById('chat-input');
  const sendButton = document.getElementById('chat-send');
  const agent = document.getElementById('chat-agent');
  const message = input.value.trim();
  if (!message) return;
  appendChatMessage('user', message);
  input.value = '';
  sendButton.disabled = true;
  let pendingReply = null;

  try {
    const fileQuery = getFileSearchQuery(message);
    if (fileQuery) {
      document.getElementById('file-name').value = fileQuery;
      await searchFiles({ preventDefault() {} }, (error, response) => {
        if (error) {
          appendChatMessage('assistant', `File search failed: ${error.message}`);
          return;
        }
        appendChatMessage('assistant', formatFileSearchReply(response));
      });
      return;
    }

    const minutes = getYoutubeLimitMinutes(message);
    if (minutes !== null) {
      if (!window.pywebview || !window.pywebview.api) {
        throw new Error('ARAVI is not available.');
      }
      const result = await window.pywebview.api.set_website_limit('youtube.com', minutes);
      document.getElementById('youtube-limit').value = result.limit_minutes;
      document.getElementById('save-status').textContent = 'Limits saved.';
      await recordDashboardActivity('website_limits');
      const unit = result.limit_minutes === 1 ? 'minute' : 'minutes';
      appendChatMessage('assistant', `Seri thala! YouTube limit ${result.limit_minutes} ${unit}-ku set panniten.`);
      return;
    }

    pendingReply = appendTypingIndicator();
    let reply;
    if (!window.pywebview || !window.pywebview.api) {
      throw new Error('ARAVI is not available.');
    }
    if (isBatteryStatusRequest(message)) {
      reply = formatLiveBatteryReply(await window.pywebview.api.get_system_stats());
    } else if (agent.value === 'web-search') {
      reply = readChatApiResult(
        await window.pywebview.api.chat_with_local_search(message, webSearchHistory)
      );
      webSearchHistory.push(
        { role: 'user', text: message },
        { role: 'model', text: reply.split('\n\nSources:\n')[0] }
      );
      webSearchHistory = webSearchHistory.slice(-12);
    } else if (agent.value === 'local-ollama') {
      reply = readChatApiResult(
        await window.pywebview.api.chat_with_local_model(message, localHistory)
      );
      localHistory.push(
        { role: 'user', text: message },
        { role: 'model', text: reply }
      );
      localHistory = localHistory.slice(-12);
    } else if (agent.value === 'opencode') {
      reply = readChatApiResult(
        await window.pywebview.api.chat_with_opencode(message, opencodeHistory)
      );
      opencodeHistory.push(
        { role: 'user', text: message },
        { role: 'model', text: reply }
      );
      opencodeHistory = opencodeHistory.slice(-12);
    } else {
      reply = readChatApiResult(await window.pywebview.api.chat_with_gemini(
          message,
          geminiHistory,
          false
        ));
      geminiHistory.push(
        { role: 'user', text: message },
        { role: 'model', text: reply }
      );
      geminiHistory = geminiHistory.slice(-12);
    }
    renderGeminiReply(pendingReply, reply);
    pendingReply.className = 'chat-message assistant-message';
    pendingReply = null;
    document.getElementById('chat-messages').lastChild.scrollIntoView?.({ block: 'nearest' });
    document.getElementById('chat-messages').scrollTop =
      document.getElementById('chat-messages').scrollHeight;
    await recordDashboardActivity('chat');
  } catch (error) {
    if (pendingReply) {
      const agentName = {
        'web-search': 'Karupu Web Search (Ollama)',
        'quick-chat': 'Karupu (Gemini)',
        'local-ollama': 'Karupu Local Ollama',
        opencode: 'Karupu (OpenCode)'
      }[agent.value] || 'Karupu';
      pendingReply.textContent = `${agentName} error: ${error.message || error}`;
      pendingReply.className = 'chat-message assistant-message';
    } else {
      appendChatMessage('assistant', `Command failed: ${error.message || error}`);
    }
  } finally {
    sendButton.disabled = false;
    input.focus();
  }
}

function readChatApiResult(result) {
  if (typeof result === 'string') return result;
  if (result && typeof result.reply === 'string') return result.reply;
  if (result && typeof result.error === 'string') throw new Error(result.error);
  throw new Error('Karupu returned an invalid chat response.');
}

function updateChatAgentBadge() {
  const agent = document.getElementById('chat-agent').value;
  const labels = {
    'web-search': '● Ollama + Tavily Search',
    'quick-chat': '✦ Karupu + Gemini',
    'local-ollama': '● Local Ollama',
    opencode: '✦ Karupu + OpenCode'
  };
  document.getElementById('chat-agent-badge').textContent = labels[agent] || labels['web-search'];
}

function isBatteryStatusRequest(message) {
  const normalized = message.toLowerCase();
  const batteryQuestion =
    /\b(?:battery|batteries|charge|charging)\b/.test(normalized) &&
    /\b(?:how much|what|level|percent(?:age)?|left|remaining|status|evvulavu|evalo|irukku?|iruka)\b/.test(normalized);
  const liveAccessQuestion =
    /(?:real[\s-]*time|live).*(?:access|asses|check|status)|(?:access|asses|check|status).*(?:real[\s-]*time|live)/.test(normalized);
  return batteryQuestion || liveAccessQuestion;
}

function formatLiveBatteryReply(stats) {
  if (!stats || typeof stats !== 'object' || Array.isArray(stats)) {
    throw new Error('ARAVI could not read the laptop system status.');
  }
  if (!Number.isFinite(stats.battery_percent) || stats.battery_percent < 0 || stats.battery_percent > 100) {
    return 'Battery status-a local-aa check panna mudiyum, aana ippo Windows-la battery reading available illa.';
  }
  const connection = typeof stats.is_plugged === 'boolean'
    ? stats.is_plugged ? '; charger connected.' : '; charger not connected.'
    : '.';
  return `Aama thala, Karupu-ku local system monitor moolama real-time battery status access irukku. Ippo battery ${Math.round(stats.battery_percent)}% irukku${connection}`;
}

function getFileSearchQuery(message) {
  const text = message.trim();
  const englishMatch = text.match(/^(?:where(?:'s| is)?|find|search(?: for)?|locate)\s+(?:the\s+)?(?:file\s+)?(.+?)[?.!]*$/i);
  const tamilMatch = text.match(/^(.+?)\s+enga(?:e)?\s+iruk(?:ku|u)[?.!]*$/i);
  const match = englishMatch || tamilMatch;
  return match ? match[1].trim().replace(/^["']|["']$/g, '') : null;
}

function getYoutubeLimitMinutes(message) {
  if (!/youtube/i.test(message) || !/(?:limit|time)/i.test(message)) return null;
  const match = message.match(/\b(\d{1,3})\s*(?:min(?:ute)?s?)\b/i);
  return match ? Number(match[1]) : null;
}

function formatFileSearchReply(response) {
  if (response.cancelled) return 'File search cancel panniten.';
  if (!response.matches.length) return 'Indha peru match aana file kidaikkala.';
  const paths = response.matches.map(match => match.path).join('\n');
  const suffix = response.truncated ? '\n50 results dhaan kaamichen; innum specific name try pannu.' : '';
  return `${response.matches.length} file match kidaichirukku:\n${paths}${suffix}`;
}

function appendChatMessage(role, text) {
  const messages = document.getElementById('chat-messages');
  const item = document.createElement('p');
  item.className = `chat-message ${role}-message`;
  item.textContent = text;
  messages.append(item);
  messages.scrollTop = messages.scrollHeight;
  return item;
}

function appendTypingIndicator() {
  const item = document.createElement('p');
  item.className = 'chat-message assistant-message typing-indicator';
  item.setAttribute('role', 'status');
  item.setAttribute('aria-label', 'Karupu is typing');
  for (let index = 0; index < 3; index += 1) {
    const dot = document.createElement('span');
    dot.className = 'typing-dot';
    item.append(dot);
  }
  const messages = document.getElementById('chat-messages');
  messages.append(item);
  messages.scrollTop = messages.scrollHeight;
  return item;
}

function renderGeminiReply(messageElement, reply) {
  const marker = '\n\nSources:\n';
  const sourceIndex = reply.lastIndexOf(marker);
  if (sourceIndex === -1) {
    messageElement.textContent = reply;
    return;
  }

  messageElement.textContent = reply.slice(0, sourceIndex);
  const sourceList = document.createElement('ul');
  sourceList.className = 'chat-sources';
  reply.slice(sourceIndex + marker.length).split('\n').forEach(line => {
    const separator = line.lastIndexOf(' | ');
    if (separator < 0) return;
    const title = line.slice(0, separator).trim();
    const rawUrl = line.slice(separator + 3).trim();
    let sourceUrl;
    try {
      sourceUrl = new URL(rawUrl);
    } catch (_error) {
      return;
    }
    if (!['http:', 'https:'].includes(sourceUrl.protocol)) return;

    const item = document.createElement('li');
    const link = document.createElement('a');
    link.href = sourceUrl.href;
    link.textContent = title || sourceUrl.hostname;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    item.append(link);
    sourceList.append(item);
  });

  if (sourceList.children.length) {
    messageElement.append(sourceList);
  }
}

async function loadObservationStatus() {
  if (!window.pywebview || !window.pywebview.api) return;

  try {
    setObservationStatus(await window.pywebview.api.get_window_observation_status());
  } catch (error) {
    document.getElementById('observation-status').textContent =
      `Could not load observation status: ${error.message || error}`;
  }
}

async function toggleObservation() {
  const button = document.getElementById('observation-toggle');
  const status = document.getElementById('observation-status');
  if (!window.pywebview || !window.pywebview.api) {
    status.textContent = 'ARAVI is not available.';
    return;
  }

  button.disabled = true;
  try {
    const isActive = await window.pywebview.api.get_window_observation_status();
    const nextStatus = isActive
      ? await window.pywebview.api.stop_window_observation()
      : await window.pywebview.api.start_window_observation();
    setObservationStatus(nextStatus);
    await loadActivityHistory();
  } catch (error) {
    status.textContent = `Could not change observation status: ${error.message || error}`;
  } finally {
    button.disabled = false;
  }
}

function setObservationStatus(isActive) {
  document.getElementById('observation-status').textContent = isActive
    ? 'Observation is on. Active window titles are shown by ARAVI.'
    : 'Observation is off.';
  document.getElementById('observation-toggle').textContent = isActive
    ? 'Stop Monitoring'
    : 'Start Monitoring';
  document.getElementById('monitor-state').textContent = isActive ? '● ON' : '● OFF';
  if (isActive && activityRefreshTimer === null) {
    activityRefreshTimer = setInterval(loadActivityHistory, 5000);
  } else if (!isActive && activityRefreshTimer !== null) {
    clearInterval(activityRefreshTimer);
    activityRefreshTimer = null;
  }
}

async function loadActivityHistory() {
  if (!window.pywebview || !window.pywebview.api) return;

  try {
    const history = await window.pywebview.api.get_app_activity_history();
    renderActivityHistory(Array.isArray(history) ? history : []);
  } catch (error) {
    document.getElementById('observation-status').textContent =
      `Could not load app activity history: ${error.message || error}`;
  }
}

async function loadDashboardHistory() {
  if (!window.pywebview || !window.pywebview.api) return;
  const status = document.getElementById('dashboard-action-status');
  try {
    const history = await window.pywebview.api.get_dashboard_activity_history();
    renderDashboardHistory(Array.isArray(history) ? history : []);
  } catch (error) {
    status.textContent = `Could not load dashboard activity: ${error.message || error}`;
  }
}

async function recordDashboardActivity(activityType) {
  if (!window.pywebview || !window.pywebview.api) return;
  const status = document.getElementById('dashboard-action-status');
  try {
    const saved = await window.pywebview.api.record_dashboard_activity(activityType);
    status.textContent = saved ? '' : 'Could not save dashboard activity.';
    await loadDashboardHistory();
  } catch (error) {
    status.textContent = `Could not save dashboard activity: ${error.message || error}`;
  }
}

function renderDashboardHistory(history) {
  const list = document.getElementById('dashboard-action-list');
  const emptyMessage = document.getElementById('dashboard-action-empty');
  const records = history
    .filter(record =>
      record &&
      typeof record.label === 'string' &&
      typeof record.timestamp === 'string'
    )
    .slice(0, 10);
  list.replaceChildren();
  emptyMessage.hidden = records.length > 0;
  records.forEach(record => {
    const item = document.createElement('li');
    const label = document.createElement('strong');
    const timestamp = document.createElement('span');
    item.className = 'activity-entry';
    label.className = 'activity-app';
    timestamp.className = 'activity-details';
    label.textContent = record.label;
    timestamp.textContent = formatActivityTimestamp(record.timestamp);
    item.append(label, timestamp);
    list.append(item);
  });
}

function renderActivityHistory(history) {
  const validRecords = history
    .filter(record =>
      record &&
      typeof record.app === 'string' &&
      typeof record.date === 'string' &&
      Number.isFinite(Number(record.seconds)) &&
      Number(record.seconds) > 0
    )
    .sort((left, right) =>
      right.date.localeCompare(left.date) || Number(right.seconds) - Number(left.seconds)
    );

  renderActivityList(
    validRecords.slice(0, 6),
    document.getElementById('dashboard-activity-list'),
    document.getElementById('dashboard-activity-empty')
  );
  renderActivityList(
    validRecords,
    document.getElementById('activity-history-list'),
    document.getElementById('activity-history-empty')
  );
}

function renderActivityList(records, list, emptyMessage) {
  list.replaceChildren();
  emptyMessage.hidden = records.length > 0;
  records.forEach(record => {
    const item = document.createElement('li');
    const app = document.createElement('strong');
    const details = document.createElement('span');
    const duration = document.createElement('span');
    item.className = 'activity-entry';
    app.className = 'activity-app';
    details.className = 'activity-details';
    duration.className = 'activity-duration';
    app.textContent = formatAppName(record.app);
    details.textContent = formatActivityDate(record.date);
    duration.textContent = formatActivityDuration(Number(record.seconds));
    details.append(duration);
    item.append(app, details);
    list.append(item);
  });
}

function formatAppName(appName) {
  const knownNames = {
    chrome: 'Google Chrome',
    msedge: 'Microsoft Edge',
    firefox: 'Mozilla Firefox',
    code: 'Visual Studio Code',
    explorer: 'File Explorer',
    winword: 'Microsoft Word',
    excel: 'Microsoft Excel',
    powerpnt: 'Microsoft PowerPoint'
  };
  const normalized = appName.toLowerCase().replace(/\.exe$/, '');
  return knownNames[normalized] ||
    normalized.replace(/[_-]+/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase());
}

function formatActivityDate(dateValue) {
  const date = new Date(`${dateValue}T00:00:00`);
  if (Number.isNaN(date.getTime())) return dateValue;
  return new Intl.DateTimeFormat('en', {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  }).format(date);
}

function formatActivityTimestamp(timestamp) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return timestamp;
  return new Intl.DateTimeFormat('en', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit'
  }).format(date);
}

function formatActivityDuration(seconds) {
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (hours) return `${hours} hr${hours === 1 ? '' : 's'}${remainingMinutes ? ` ${remainingMinutes} min` : ''}`;
  if (minutes) return `${minutes} min`;
  return `${Math.floor(seconds)} sec`;
}

function getSite(domain, sites) {
  return sites.find(site =>
    typeof site.domain === 'string' &&
    site.domain.toLowerCase().replace(/^www\./, '') === domain
  );
}

function updateSiteUsage(site, limitMinutes, siteKey) {
  const usedSeconds = Number(site && site.used_seconds) || 0;
  const usedMinutes = Math.floor(usedSeconds / 60);
  document.getElementById(`${siteKey}-usage-label`).textContent = `${usedMinutes} min used`;
  const usagePercent = limitMinutes > 0
    ? Math.min(100, (usedSeconds / (limitMinutes * 60)) * 100)
    : 0;
  document.getElementById(`${siteKey}-usage-bar`).style.width = `${usagePercent}%`;
}

async function loadLimits() {
  if (!window.pywebview || !window.pywebview.api) return;

  try {
    const config = await window.pywebview.api.get_config();
    const sites = config.tracked_websites || [];
    SITE_DEFAULTS.forEach(site => {
      const saved = getSite(site.domain, sites);
      const limitMinutes = saved ? saved.limit_minutes : site.fallback;
      document.getElementById(site.inputId).value = limitMinutes;
      updateSiteUsage(saved, limitMinutes, site.inputId.replace('-limit', ''));
    });
  } catch (error) {
    document.getElementById('save-status').textContent = 'Could not load saved limits.';
  }
}

async function saveLimits(event) {
  event.preventDefault();
  const status = document.getElementById('save-status');
  if (!window.pywebview || !window.pywebview.api) return;

  try {
    const config = await window.pywebview.api.get_config();
    const trackedSites = Array.isArray(config.tracked_websites)
      ? [...config.tracked_websites]
      : [];
    SITE_DEFAULTS.forEach(site => {
      const existing = getSite(site.domain, trackedSites);
      if (existing) {
        existing.limit_minutes = Number(document.getElementById(site.inputId).value);
        updateSiteUsage(existing, existing.limit_minutes, site.inputId.replace('-limit', ''));
      } else {
        const addedSite = {
          domain: site.domain,
          limit_minutes: Number(document.getElementById(site.inputId).value),
          used_seconds: 0
        };
        trackedSites.push(addedSite);
        updateSiteUsage(addedSite, addedSite.limit_minutes, site.inputId.replace('-limit', ''));
      }
    });
    config.tracked_websites = trackedSites;
    const saved = await window.pywebview.api.save_config(config);
    status.textContent = saved ? 'Limits saved.' : 'Could not save limits.';
    if (saved) await recordDashboardActivity('website_limits');
  } catch (error) {
    status.textContent = `Could not save limits: ${error.message || error}`;
  }
}

async function refreshWaterReminderStatus() {
  if (!window.pywebview || !window.pywebview.api) return;

  try {
    const status = await window.pywebview.api.get_water_reminder_status();
    const intervalInput = document.getElementById('water-reminder-interval');
    if (document.activeElement !== intervalInput) {
      intervalInput.value = status.interval_minutes;
    }
    if (status.pending && !waterReminderPendingShown) {
      waterReminderPendingShown = true;
      showPage('limits-panel');
      document.getElementById('water-reminder-response-status').textContent = '';
      document.getElementById('water-reminder-dialog').hidden = false;
    } else if (!status.pending) {
      waterReminderPendingShown = false;
      document.getElementById('water-reminder-dialog').hidden = true;
    }
  } catch (error) {
    document.getElementById('water-reminder-status').textContent =
      `Could not load water reminder settings: ${error.message || error}`;
  }
}

async function saveWaterReminderInterval(event) {
  event.preventDefault();
  const status = document.getElementById('water-reminder-status');
  const interval = Number(document.getElementById('water-reminder-interval').value);
  status.textContent = '';

  try {
    await window.pywebview.api.set_water_reminder_interval(interval);
    waterReminderPendingShown = false;
    document.getElementById('water-reminder-dialog').hidden = true;
    status.textContent = `Water reminder saved. ARAVI will remind you every ${interval} minutes.`;
  } catch (error) {
    status.textContent = `Could not save water reminder: ${error.message || error}`;
  }
}

async function respondToWaterReminder(answer) {
  const buttons = [
    document.getElementById('water-reminder-yes'),
    document.getElementById('water-reminder-no')
  ];
  const responseStatus = document.getElementById('water-reminder-response-status');
  buttons.forEach(button => {
    button.disabled = true;
  });
  responseStatus.textContent = '';

  try {
    const result = await window.pywebview.api.respond_to_water_reminder(answer);
    waterReminderPendingShown = false;
    document.getElementById('water-reminder-dialog').hidden = true;
    document.getElementById('water-reminder-status').textContent = answer === 'yes'
      ? `Great! The next reminder is in ${result.next_reminder_minutes} minutes.`
      : `Okay, ARAVI will remind you again in ${result.next_reminder_minutes} minutes.`;
  } catch (error) {
    responseStatus.textContent = `Could not save your response: ${error.message || error}`;
  } finally {
    buttons.forEach(button => {
      button.disabled = false;
    });
  }
}
