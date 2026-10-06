const DEFAULT_LIMIT_MINUTES = 30;
const WARNING_SECONDS = 10;
const HEARTBEAT_MAX_SECONDS = 8;
const WARNING_ALARM = 'aravi-youtube-limit-warning';
const WARNING_NOTIFICATION = 'aravi-youtube-limit';

let statePromise;
let processingMessages = Promise.resolve();
let warningTimeout = null;

function getTodayKey() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

function loadState() {
  if (!statePromise) {
    statePromise = chrome.storage.local.get({
      limitMinutes: DEFAULT_LIMIT_MINUTES,
      usageSeconds: 0,
      usageDate: getTodayKey(),
      playbackTabs: {},
      warning: null
    });
  }
  return statePromise.then(async state => {
    if (state.usageDate !== getTodayKey()) {
      state.usageSeconds = 0;
      state.playbackTabs = {};
      state.warning = null;
      state.usageDate = getTodayKey();
      await saveState(state);
    }
    return state;
  });
}

async function saveState(state) {
  await chrome.storage.local.set({
    limitMinutes: state.limitMinutes,
    usageSeconds: state.usageSeconds,
    usageDate: state.usageDate,
    playbackTabs: state.playbackTabs,
    warning: state.warning
  });
}

function clearWarningTimer() {
  if (warningTimeout !== null) {
    clearTimeout(warningTimeout);
    warningTimeout = null;
  }
}

async function closeLimitedTab(tabId) {
  const state = await loadState();
  const warning = state.warning;
  if (!warning || warning.tabId !== tabId) return;

  clearWarningTimer();
  try {
    await chrome.tabs.remove(tabId);
    state.usageSeconds = 0;
    state.playbackTabs[String(tabId)] = {
      isPlaying: false,
      lastHeartbeatAt: Date.now()
    };
  } catch (error) {
    console.warn('Could not close the YouTube tab at its time limit:', error);
  }

  state.warning = null;
  await saveState(state);
  await chrome.notifications.clear(WARNING_NOTIFICATION);
  await chrome.alarms.clear(WARNING_ALARM);
}

async function beginWarning(tabId) {
  const state = await loadState();
  if (state.warning) return;

  state.warning = {
    tabId,
    deadline: Date.now() + WARNING_SECONDS * 1000
  };
  await saveState(state);
  await chrome.notifications.create(WARNING_NOTIFICATION, {
    type: 'basic',
    iconUrl: chrome.runtime.getURL('icons/aravi.png'),
    title: 'ARAVI: YouTube time limit reached',
    message: `This YouTube tab will close in ${WARNING_SECONDS} seconds.`,
    priority: 2,
    requireInteraction: true
  });

  clearWarningTimer();
  warningTimeout = setTimeout(() => {
    void closeLimitedTab(tabId);
  }, WARNING_SECONDS * 1000);
  chrome.alarms.create(WARNING_ALARM, { delayInMinutes: 0.5 });
}

async function restoreWarning() {
  const state = await loadState();
  if (!state.warning) return;

  const remainingMs = Math.max(0, state.warning.deadline - Date.now());
  if (remainingMs === 0) {
    await closeLimitedTab(state.warning.tabId);
    return;
  }

  clearWarningTimer();
  warningTimeout = setTimeout(() => {
    void closeLimitedTab(state.warning.tabId);
  }, remainingMs);
  chrome.alarms.create(WARNING_ALARM, { delayInMinutes: 0.5 });
}

async function handlePlayback(message, sender) {
  const tabId = sender.tab && sender.tab.id;
  if (typeof tabId !== 'number') return;

  const state = await loadState();
  const now = Date.now();
  const key = String(tabId);
  const previous = state.playbackTabs[key] || {
    isPlaying: false,
    lastHeartbeatAt: now
  };

  if (previous.isPlaying) {
    const elapsed = Math.min(
      HEARTBEAT_MAX_SECONDS,
      Math.max(0, (now - previous.lastHeartbeatAt) / 1000)
    );
    state.usageSeconds += elapsed;
  }

  state.playbackTabs[key] = {
    isPlaying: Boolean(message.isPlaying),
    lastHeartbeatAt: now
  };
  await saveState(state);

  if (
    !state.warning &&
    state.usageSeconds >= state.limitMinutes * 60
  ) {
    await beginWarning(tabId);
  }
}

async function getStatus() {
  const state = await loadState();
  const activePlayback = Object.values(state.playbackTabs).some(tab =>
    tab.isPlaying && Date.now() - tab.lastHeartbeatAt <= HEARTBEAT_MAX_SECONDS * 2000
  );
  return {
    limitMinutes: state.limitMinutes,
    usageSeconds: Math.floor(state.usageSeconds),
    isPlaying: activePlayback,
    warning: state.warning
  };
}

async function setLimit(minutes) {
  if (!Number.isInteger(minutes) || minutes < 1 || minutes > 300) {
    throw new Error('The limit must be a whole number between 1 and 300 minutes.');
  }

  const state = await loadState();
  state.limitMinutes = minutes;
  await saveState(state);
  return getStatus();
}

async function resetUsage() {
  const state = await loadState();
  state.usageSeconds = 0;
  state.playbackTabs = {};
  state.warning = null;
  await saveState(state);
  clearWarningTimer();
  await chrome.alarms.clear(WARNING_ALARM);
  await chrome.notifications.clear(WARNING_NOTIFICATION);
  return getStatus();
}

async function handleMessage(message, sender) {
  if (!message || typeof message.type !== 'string') return null;

  if (message.type === 'youtube-playback') {
    await handlePlayback(message, sender);
    return null;
  }
  if (message.type === 'get-status') return getStatus();
  if (message.type === 'set-limit') return setLimit(message.minutes);
  if (message.type === 'reset-usage') return resetUsage();
  return null;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  processingMessages = processingMessages
    .then(() => handleMessage(message, sender))
    .then(result => sendResponse({ ok: true, result }))
    .catch(error => {
      console.error('ARAVI YouTube limit request failed:', error);
      sendResponse({ ok: false, error: error.message });
    });
  return true;
});

chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === WARNING_ALARM) {
    void restoreWarning();
  }
});

chrome.tabs.onRemoved.addListener(tabId => {
  processingMessages = processingMessages.then(async () => {
    const state = await loadState();
    delete state.playbackTabs[String(tabId)];
    if (state.warning && state.warning.tabId === tabId) {
      state.warning = null;
      clearWarningTimer();
      await chrome.notifications.clear(WARNING_NOTIFICATION);
      await chrome.alarms.clear(WARNING_ALARM);
    }
    await saveState(state);
  }).catch(error => console.error('Could not clear closed-tab playback state:', error));
});

chrome.notifications.onClicked.addListener(async notificationId => {
  if (notificationId !== WARNING_NOTIFICATION) return;
  const state = await loadState();
  if (!state.warning) return;
  try {
    const tab = await chrome.tabs.get(state.warning.tabId);
    await chrome.windows.update(tab.windowId, { focused: true });
    await chrome.tabs.update(tab.id, { active: true });
  } catch (error) {
    console.warn('Could not focus the YouTube tab:', error);
  }
});

chrome.runtime.onInstalled.addListener(() => {
  void restoreWarning();
  void injectIntoExistingYouTubeTabs();
});

chrome.runtime.onStartup.addListener(() => {
  void restoreWarning();
  void injectIntoExistingYouTubeTabs();
});

async function injectIntoExistingYouTubeTabs() {
  const tabs = await chrome.tabs.query({
    url: [
      'https://www.youtube.com/*',
      'https://youtube.com/*',
      'https://youtu.be/*'
    ]
  });
  for (const tab of tabs) {
    if (typeof tab.id !== 'number') continue;
    try {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ['content.js']
      });
    } catch (error) {
      console.warn('Could not start YouTube playback tracking in an existing tab:', error);
    }
  }
}

void restoreWarning();
