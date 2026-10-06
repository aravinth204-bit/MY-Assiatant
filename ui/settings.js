const SITE_DEFAULTS = [
  { domain: 'youtube.com', inputId: 'youtube-limit', fallback: 30 },
  { domain: 'instagram.com', inputId: 'instagram-limit', fallback: 20 }
];

let activeFileSearchId = null;
let fileSearchPollTimer = null;
let fileSearchPollPending = false;
let activeFileSearchOnComplete = null;
let geminiHistory = [];

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('limits-form').addEventListener('submit', saveLimits);
  document.getElementById('file-search-form').addEventListener('submit', searchFiles);
  document.getElementById('chat-form').addEventListener('submit', handleChatMessage);
  document.getElementById('file-search-cancel').addEventListener('click', cancelFileSearch);
  document.getElementById('observation-toggle').addEventListener('click', toggleObservation);
  loadLimits();
  loadObservationStatus();
  loadChatStatus();
});

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
  const message = input.value.trim();
  if (!message) return;
  appendChatMessage('user', message);
  input.value = '';
  sendButton.disabled = true;

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
      const unit = result.limit_minutes === 1 ? 'minute' : 'minutes';
      appendChatMessage('assistant', `Seri thala! YouTube limit ${result.limit_minutes} ${unit}-ku set panniten.`);
      return;
    }

    appendChatMessage(
      'assistant',
      'Gemini-kitta ketkaren...'
    );
    const reply = await window.pywebview.api.chat_with_gemini(message, geminiHistory);
    geminiHistory.push(
      { role: 'user', text: message },
      { role: 'model', text: reply }
    );
    geminiHistory = geminiHistory.slice(-12);
    document.getElementById('chat-messages').lastChild.textContent = reply;
    document.getElementById('chat-messages').scrollTop =
      document.getElementById('chat-messages').scrollHeight;
  } catch (error) {
    const lastMessage = document.getElementById('chat-messages').lastChild;
    if (lastMessage && lastMessage.textContent === 'Gemini-kitta ketkaren...') {
      lastMessage.textContent = `Gemini error: ${error.message || error}`;
    } else {
      appendChatMessage('assistant', `Command failed: ${error.message || error}`);
    }
  } finally {
    sendButton.disabled = false;
    input.focus();
  }
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
}

async function loadChatStatus() {
  const status = document.getElementById('chat-connection-status');
  if (!window.pywebview || !window.pywebview.api) {
    status.textContent = 'ARAVI is not available.';
    return;
  }

  try {
    const result = await window.pywebview.api.get_chat_status();
    status.textContent = result.gemini_configured
      ? 'Gemini is ready. General chat messages are sent to Google.'
      : 'Gemini API key is not set. Set GEMINI_API_KEY in Windows, then restart ARAVI.';
  } catch (error) {
    status.textContent = `Could not check Gemini setup: ${error.message || error}`;
  }
}

async function loadObservationStatus() {
  if (!window.pywebview || !window.pywebview.api) return;

  try {
    setObservationStatus(await window.pywebview.api.get_window_observation_status());
  } catch (error) {
    document.getElementById('observation-status').textContent = 'Could not load observation status.';
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
  } catch (error) {
    status.textContent = 'Could not change observation status.';
  } finally {
    button.disabled = false;
  }
}

function setObservationStatus(isActive) {
  document.getElementById('observation-status').textContent = isActive
    ? 'Observation is on. Active window titles are shown by ARAVI.'
    : 'Observation is off.';
  document.getElementById('observation-toggle').textContent = isActive
    ? 'Stop observing'
    : 'Start observing';
}

function getSite(domain, sites) {
  return sites.find(site =>
    typeof site.domain === 'string' &&
    site.domain.toLowerCase().replace(/^www\./, '') === domain
  );
}

async function loadLimits() {
  if (!window.pywebview || !window.pywebview.api) return;

  try {
    const config = await window.pywebview.api.get_config();
    const sites = config.tracked_websites || [];
    SITE_DEFAULTS.forEach(site => {
      const saved = getSite(site.domain, sites);
      document.getElementById(site.inputId).value = saved ? saved.limit_minutes : site.fallback;
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
      } else {
        trackedSites.push({
          domain: site.domain,
          limit_minutes: Number(document.getElementById(site.inputId).value),
          used_seconds: 0
        });
      }
    });
    config.tracked_websites = trackedSites;
    const saved = await window.pywebview.api.save_config(config);
    status.textContent = saved ? 'Limits saved.' : 'Could not save limits.';
  } catch (error) {
    status.textContent = 'Could not save limits.';
  }
}
