const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const settingsSource = fs.readFileSync(
  path.join(__dirname, '..', 'ui', 'settings.js'),
  'utf8'
);
const settingsHtml = fs.readFileSync(
  path.join(__dirname, '..', 'ui', 'settings.html'),
  'utf8'
);
const settingsCss = fs.readFileSync(
  path.join(__dirname, '..', 'ui', 'settings.css'),
  'utf8'
);

function createSettingsHarness(config, fileSearch = async () => ({
  matches: [],
  skipped_directories: 0,
  skipped_items: 0,
  truncated: false
}), searchApi = {}, chatApi = {}, activityApi = {}) {
  const listeners = {};
  const intervals = new Map();
  let nextIntervalId = 0;
  let fileSearchIntervalId = null;
  const pageClickListeners = {};
  const pageLinks = [
    'dashboard-panel',
    'chat-panel',
    'mascot-panel',
    'voice-panel',
    'personality-panel',
    'analytics-panel',
    'file-panel',
    'limits-panel',
    'activity-panel'
  ]
    .map(page => ({
      dataset: { page },
      classList: {
        active: page === 'dashboard-panel',
        toggle(name, enabled) {
          this[name] = enabled;
        }
      },
      addEventListener: (event, handler) => {
        if (event === 'click') pageClickListeners[page] = handler;
      }
    }));
  const pagePanels = pageLinks.map(link => ({
    id: link.dataset.page,
    hidden: link.dataset.page !== 'dashboard-panel'
  }));
  const activityEvents = [];
  let waterReminderInterval = 60;
  let waterReminderPending = false;
  const makeActivityList = () => ({
    items: [],
    replaceChildren() {
      this.items = [];
    },
    append(item) {
      this.items.push(item);
    }
  });
  const elements = {
    'water-reminder-form': {
      addEventListener: (event, handler) => {
        listeners.waterReminder = handler;
      }
    },
    'water-reminder-interval': { value: '60' },
    'water-reminder-status': { textContent: '' },
    'water-reminder-dialog': { hidden: true },
    'water-reminder-response-status': { textContent: '' },
    'water-reminder-yes': {
      disabled: false,
      addEventListener: (event, handler) => {
        listeners.waterReminderYes = handler;
      }
    },
    'water-reminder-no': {
      disabled: false,
      addEventListener: (event, handler) => {
        listeners.waterReminderNo = handler;
      }
    },
    'limits-form': {
      addEventListener: (event, handler) => {
        listeners.submit = handler;
      }
    },
    'file-search-form': {
      addEventListener: (event, handler) => {
        listeners.fileSearch = handler;
      }
    },
    'file-search-cancel': {
      hidden: true,
      addEventListener: (event, handler) => {
        listeners.fileSearchCancel = handler;
      }
    },
    'file-search-submit': { disabled: false },
    'file-name': { value: 'invoice.pdf' },
    'file-search-status': { textContent: '' },
    'file-search-progress': { textContent: '' },
    'chat-form': {
      addEventListener: (event, handler) => {
        listeners.chat = handler;
      }
    },
    'chat-input': {
      value: '',
      focus() {}
    },
    'chat-agent': {
      value: 'web-search',
      addEventListener: (event, handler) => {
        listeners.chatAgentChange = handler;
      }
    },
    'chat-agent-badge': { textContent: '' },
    'chat-title': { textContent: '' },
    'chat-send': { disabled: false },
    'mascot-status': { textContent: '' },
    'voice-status': { textContent: '' },
    'voice-enabled': {
      checked: false,
      addEventListener: (event, handler) => {
        listeners.voiceEnabledChange = handler;
      }
    },
    'voice-language': {
      value: 'en-IN',
      addEventListener: (event, handler) => {
        listeners.voiceLanguageChange = handler;
      }
    },
    'personality-status': { textContent: '' },
    'weekly-status': { innerHTML: '' },
    'monthly-status': { innerHTML: '' },
    'productivity-status': { innerHTML: '' },
    'resource-status': { innerHTML: '' },
    'analytics-status': { textContent: '' },
    'chat-messages': {
      children: [],
      scrollTop: 0,
      scrollHeight: 0,
      get lastChild() {
        return this.children.at(-1);
      },
      append(item) {
        this.children.push(item);
        this.scrollHeight += 1;
      }
    },
    'file-search-results': {
      items: [],
      replaceChildren() {
        this.items = [];
      },
      append(item) {
        this.items.push(item);
      }
    },
    'youtube-limit': { value: '15' },
    'instagram-limit': { value: '25' },
    'youtube-usage-label': { textContent: '' },
    'instagram-usage-label': { textContent: '' },
    'youtube-usage-bar': { style: {} },
    'instagram-usage-bar': { style: {} },
    'save-status': { textContent: '' },
    'observation-status': { textContent: '' },
    'monitor-state': { textContent: '' },
    'dashboard-action-list': makeActivityList(),
    'dashboard-action-empty': { hidden: false },
    'dashboard-action-status': { textContent: '' },
    'dashboard-activity-list': makeActivityList(),
    'dashboard-activity-empty': { hidden: false },
    'activity-history-list': makeActivityList(),
    'activity-history-empty': { hidden: false },
    'observation-toggle': {
      textContent: '',
      disabled: false,
      addEventListener: (event, handler) => {
        listeners.observationToggle = handler;
      }
    }
  };
  let savedConfig;
  let observationActive = false;

  const context = {
    document: {
      addEventListener: (event, handler) => {
        listeners.domContentLoaded = handler;
      },
      getElementById: id => elements[id],
      activeElement: null,
      querySelectorAll: () => [],
      createElement: tagName => ({
        tagName,
        children: [],
        className: '',
        attributes: {},
        _textContent: '',
        get textContent() {
          return this._textContent;
        },
        set textContent(value) {
          this._textContent = value;
          this.children = [];
        },
        setAttribute(name, value) {
          this.attributes[name] = value;
        },
        append(...children) {
          this.children.push(...children);
        }
      })
    },
    window: {
      pywebview: {
        api: {
          get_config: async () => JSON.parse(JSON.stringify(config)),
          get_water_reminder_status: async () => ({
            interval_minutes: waterReminderInterval,
            pending: waterReminderPending
          }),
          set_water_reminder_interval: async minutes => {
            waterReminderInterval = minutes;
            waterReminderPending = false;
            return { interval_minutes: minutes, pending: false };
          },
          respond_to_water_reminder: async answer => {
            waterReminderPending = false;
            return { next_reminder_minutes: answer === 'yes' ? waterReminderInterval : 10 };
          },
          search_files: fileSearch,
          start_file_search: searchApi.start || (async () => 'search-1'),
          get_file_search_status: searchApi.getStatus || (async () => ({
            status: 'completed',
            matches: [],
            scanned_directories: 1,
            scanned_entries: 4,
            skipped_directories: 0,
            skipped_items: 0,
            match_count: 0,
            truncated: false,
            cancelled: false,
            current_path: ''
          })),
          cancel_file_search: searchApi.cancel || (async () => true),
          set_website_limit: chatApi.setWebsiteLimit || (async (_domain, minutes) => ({
            domain: 'youtube.com',
            limit_minutes: minutes
          })),
          get_system_stats: chatApi.getSystemStats || (async () => ({
            battery_percent: 100,
            is_plugged: true
          })),
          get_chat_status: chatApi.getChatStatus || (async () => ({
            gemini_configured: true
          })),
          chat_with_gemini: chatApi.chatWithGemini || (async () => 'Vanakkam!'),
          chat_with_local_model: chatApi.chatWithLocalModel || (async () => 'Local reply'),
          chat_with_local_search: chatApi.chatWithLocalSearch || (async () => 'Searched local reply'),
          chat_with_opencode: chatApi.chatWithOpenCode || (async () => 'OpenCode reply'),
          get_window_observation_status: async () => observationActive,
          get_app_activity_history: activityApi.getHistory || (async () => config.app_activity_history || []),
          get_dashboard_activity_history: activityApi.getDashboardHistory ||
            (async () => config.dashboard_activity_history || []),
          record_dashboard_activity: activityApi.record ||
            (async activityType => {
              activityEvents.push(activityType);
              return true;
            }),
          start_window_observation: async () => {
            observationActive = true;
            return observationActive;
          },
          stop_window_observation: async () => {
            observationActive = false;
            return observationActive;
          },
          save_config: async nextConfig => {
            savedConfig = nextConfig;
            return true;
          }
        },
        setInterval(callback) {
          const id = ++nextIntervalId;
          intervals.set(id, callback);
          if (callback.name === 'pollFileSearch') fileSearchIntervalId = id;
          return id;
        },
        clearInterval(id) {
          intervals.delete(id);
        }
      }
    },
    Intl,
    URL,
    location: { hash: '' },
    addEventListener: (event, handler) => {
      listeners[event] = handler;
    },
    setInterval(callback) {
      const id = ++nextIntervalId;
      intervals.set(id, callback);
      if (callback.name === 'pollFileSearch') fileSearchIntervalId = id;
      return id;
    },
    clearInterval(id) {
      intervals.delete(id);
    },
    pageLinks,
    pagePanels
  };
  context.document.querySelectorAll = selector => {
    if (selector === '[data-page]') return pageLinks;
    if (selector === '.nav-btn') return pageLinks;
    if (selector === '.page-panel') return pagePanels;
    return [];
  };
  context.window.location = context.location;
  context.window.addEventListener = context.addEventListener;

  vm.runInNewContext(settingsSource, context);
  listeners.domContentLoaded();

  return {
    elements,
    listeners,
    pageClickListeners,
    pagePanels,
    pageLinks,
    activityEvents,
    getSavedConfig: () => savedConfig,
    async pollFileSearch() {
      const callback = intervals.get(fileSearchIntervalId);
      if (callback) await callback();
    }
  };
}

test('chat page uses the available height without welcome prompts or unavailable banner', () => {
  const chatMarkup = settingsHtml.match(/<section class="dashboard-content page-panel chat-panel" id="chat-panel"[\s\S]*?<\/section>/)[0];
  assert.match(chatMarkup, /Chat with Karupu/);
  assert.match(chatMarkup, /Ask Karupu anything/);
  assert.match(chatMarkup, /Karupu: Gemini/);
  assert.doesNotMatch(chatMarkup, /Vanakkam! File thedanuma/);
  assert.doesNotMatch(chatMarkup, /Try these:|data-chat-prompt|chat-connection-status|ARAVI is not available/);
  assert.match(settingsCss, /\.chat-panel\s*\{[^}]*height:\s*calc\(100vh - 64px\)/);
  assert.match(settingsCss, /\.chat-messages\s*\{[^}]*flex:\s*1 1 auto/);
});

test('Website Limits shows the water reminder setting before the daily limit controls', () => {
  const waterFormIndex = settingsHtml.indexOf('id="water-reminder-form"');
  const limitsFormIndex = settingsHtml.indexOf('id="limits-form"');

  assert.ok(waterFormIndex >= 0);
  assert.ok(waterFormIndex < limitsFormIndex);
  assert.match(settingsHtml, /id="water-reminder-interval"[^>]*min="1" max="300"/);
  assert.match(settingsHtml, /Untitled%20design%20\(3\)\.gif/);
  assert.match(settingsHtml, /id="water-reminder-yes"/);
  assert.match(settingsHtml, /id="water-reminder-no"/);
});

test('water reminder setting saves the requested interval and displays confirmation', async () => {
  const harness = createSettingsHarness({ tracked_websites: [] });
  harness.elements['water-reminder-interval'].value = '30';
  await harness.listeners.waterReminder({ preventDefault() {} });

  assert.equal(harness.elements['water-reminder-status'].textContent,
    'Water reminder saved. ARAVI will remind you every 30 minutes.');
  assert.equal(harness.elements['water-reminder-dialog'].hidden, true);
});

test('sidebar navigation opens one matching page at a time', async () => {
  const harness = createSettingsHarness({ tracked_websites: [] });
  await new Promise(resolve => setImmediate(resolve));

  harness.pageClickListeners['chat-panel']();
  assert.equal(harness.pagePanels.find(panel => panel.id === 'chat-panel').hidden, false);
  assert.equal(harness.pagePanels.find(panel => panel.id === 'dashboard-panel').hidden, true);
  assert.equal(harness.pageLinks.find(link => link.dataset.page === 'chat-panel').classList.active, true);

  harness.pageClickListeners['limits-panel']();
  assert.equal(harness.pagePanels.find(panel => panel.id === 'limits-panel').hidden, false);
  assert.equal(harness.pagePanels.filter(panel => !panel.hidden).length, 1);

  for (const page of ['mascot-panel', 'voice-panel', 'personality-panel', 'analytics-panel']) {
    harness.pageClickListeners[page]();
    assert.equal(harness.pagePanels.find(panel => panel.id === page).hidden, false);
    assert.equal(harness.pagePanels.filter(panel => !panel.hidden).length, 1);
  }
});

test('dashboard and activity monitor render persisted app usage history', async () => {
  const harness = createSettingsHarness(
    { tracked_websites: [] },
    undefined,
    {},
    {},
    {
      getHistory: async () => [
        { date: '2026-10-07', app: 'chrome', seconds: 3720 },
        { date: '2026-10-06', app: 'Code.exe', seconds: 45 }
      ]
    }
  );
  await new Promise(resolve => setImmediate(resolve));

  assert.equal(harness.elements['dashboard-activity-list'].items.length, 2);
  assert.equal(harness.elements['dashboard-activity-list'].items[0].children[0].textContent, 'Google Chrome');
  assert.equal(harness.elements['dashboard-activity-list'].items[0].children[1].children[0].textContent, '1 hr 2 min');
  assert.equal(harness.elements['activity-history-list'].items.length, 2);
  assert.equal(harness.elements['activity-history-list'].items[1].children[0].textContent, 'Visual Studio Code');
  assert.equal(harness.elements['activity-history-empty'].hidden, true);
});

test('dashboard displays privacy-safe ARAVI action history', async () => {
  const harness = createSettingsHarness(
    { tracked_websites: [] },
    undefined,
    {},
    {},
    {
      getDashboardHistory: async () => [
        { timestamp: '2026-10-07T10:30+05:30', label: 'Searched local file names' },
        { timestamp: '2026-10-07T09:20+05:30', label: 'Chat with ARAVI' }
      ]
    }
  );
  await new Promise(resolve => setImmediate(resolve));

  const events = harness.elements['dashboard-action-list'].items;
  assert.equal(events.length, 2);
  assert.equal(events[0].children[0].textContent, 'Searched local file names');
  assert.equal(events[1].children[0].textContent, 'Chat with ARAVI');
  assert.equal(harness.elements['dashboard-action-empty'].hidden, true);
});

test('saving limits preserves other sites and existing usage', async () => {
  const harness = createSettingsHarness({
    tracked_websites: [
      { domain: 'youtube.com', limit_minutes: 10, used_seconds: 120 },
      { domain: 'instagram.com', limit_minutes: 20, used_seconds: 60 },
      { domain: 'example.com', limit_minutes: 12, used_seconds: 30, custom: 'keep' }
    ]
  });

  await new Promise(resolve => setImmediate(resolve));
  harness.elements['youtube-limit'].value = '15';
  harness.elements['instagram-limit'].value = '25';
  await harness.listeners.submit({ preventDefault() {} });

  const savedSites = harness.getSavedConfig().tracked_websites;
  assert.equal(savedSites.length, 3);
  assert.deepEqual(JSON.parse(JSON.stringify(savedSites[2])), {
    domain: 'example.com',
    limit_minutes: 12,
    used_seconds: 30,
    custom: 'keep'
  });
  assert.equal(savedSites[0].limit_minutes, 15);
  assert.equal(savedSites[0].used_seconds, 120);
  assert.equal(savedSites[1].limit_minutes, 25);
  assert.equal(savedSites[1].used_seconds, 60);
  assert.deepEqual(harness.activityEvents, ['website_limits']);
});

test('saving limits recognizes www aliases without adding duplicate entries', async () => {
  const harness = createSettingsHarness({
    tracked_websites: [
      { domain: 'www.youtube.com', limit_minutes: 10, used_seconds: 5 },
      { domain: 'www.instagram.com', limit_minutes: 20, used_seconds: 8 }
    ]
  });

  await new Promise(resolve => setImmediate(resolve));
  harness.elements['youtube-limit'].value = '15';
  harness.elements['instagram-limit'].value = '25';
  await harness.listeners.submit({ preventDefault() {} });

  const savedSites = harness.getSavedConfig().tracked_websites;
  assert.equal(savedSites.length, 2);
  assert.equal(savedSites[0].limit_minutes, 15);
  assert.equal(savedSites[1].limit_minutes, 25);
});

test('loading limits shows saved daily usage in the dashboard', async () => {
  const harness = createSettingsHarness({
    tracked_websites: [
      { domain: 'youtube.com', limit_minutes: 10, used_seconds: 120 },
      { domain: 'instagram.com', limit_minutes: 20, used_seconds: 600 }
    ]
  });
  await new Promise(resolve => setImmediate(resolve));

  assert.equal(harness.elements['youtube-usage-label'].textContent, '2 min used');
  assert.equal(harness.elements['youtube-usage-bar'].style.width, '20%');
  assert.equal(harness.elements['instagram-usage-label'].textContent, '10 min used');
  assert.equal(harness.elements['instagram-usage-bar'].style.width, '50%');
});

test('activity observation can be started and stopped explicitly', async () => {
  const harness = createSettingsHarness({ tracked_websites: [] });
  await new Promise(resolve => setImmediate(resolve));

  assert.equal(harness.elements['observation-status'].textContent, 'Observation is off.');
  assert.equal(harness.elements['observation-toggle'].textContent, 'Start Monitoring');
  assert.equal(harness.elements['monitor-state'].textContent, '● OFF');

  await harness.listeners.observationToggle();
  assert.equal(harness.elements['observation-status'].textContent, 'Observation is on. Active window titles are shown by ARAVI.');
  assert.equal(harness.elements['observation-toggle'].textContent, 'Stop Monitoring');
  assert.equal(harness.elements['monitor-state'].textContent, '● ON');

  await harness.listeners.observationToggle();
  assert.equal(harness.elements['observation-status'].textContent, 'Observation is off.');
  assert.equal(harness.elements['observation-toggle'].textContent, 'Start Monitoring');
});

test('file search displays names and full paths from the local API', async () => {
  let searchedQuery;
  const harness = createSettingsHarness(
    { tracked_websites: [] },
    undefined,
    {
      start: async query => {
        searchedQuery = query;
        return 'search-result';
      },
      getStatus: async () => ({
        status: 'completed',
        matches: [{ name: '<invoice>.pdf', path: 'D:\\Documents\\<invoice>.pdf' }],
        scanned_directories: 10,
        scanned_entries: 100,
        match_count: 1,
        skipped_directories: 2,
        skipped_items: 1,
        truncated: false,
        cancelled: false,
        current_path: ''
      })
    }
  );
  await new Promise(resolve => setImmediate(resolve));

  await harness.listeners.fileSearch({ preventDefault() {} });
  await harness.pollFileSearch();

  assert.equal(searchedQuery, 'invoice.pdf');
  assert.equal(harness.elements['file-search-results'].items.length, 1);
  const [item] = harness.elements['file-search-results'].items;
  assert.equal(item.children[0].textContent, '<invoice>.pdf');
  assert.equal(item.children[1].textContent, 'D:\\Documents\\<invoice>.pdf');
  assert.equal(
    harness.elements['file-search-status'].textContent,
    '1 file found. 2 folders could not be accessed. 1 item could not be checked.'
  );
});

test('file search shows live progress and then reports completed results', async () => {
  let readCount = 0;
  const harness = createSettingsHarness(
    { tracked_websites: [] },
    undefined,
    {
      start: async () => 'search-live',
      getStatus: async () => {
        readCount += 1;
        return readCount === 1
          ? {
              status: 'running',
              scanned_directories: 12,
              scanned_entries: 1430,
              match_count: 2,
              current_path: 'C:\\Users\\Test\\Documents',
              matches: [],
              skipped_directories: 0,
              skipped_items: 0,
              truncated: false,
              cancelled: false
            }
          : {
              status: 'completed',
              scanned_directories: 20,
              scanned_entries: 2500,
              match_count: 1,
              current_path: '',
              matches: [{ name: 'resume.pdf', path: 'C:\\Users\\Test\\resume.pdf' }],
              skipped_directories: 0,
              skipped_items: 0,
              truncated: false,
              cancelled: false
            };
      }
    }
  );
  await new Promise(resolve => setImmediate(resolve));

  await harness.listeners.fileSearch({ preventDefault() {} });
  assert.equal(harness.elements['file-search-submit'].disabled, true);
  assert.equal(harness.elements['file-search-cancel'].hidden, false);
  await harness.pollFileSearch();
  assert.match(harness.elements['file-search-progress'].textContent, /12 folders, 1,430 items checked/);
  assert.match(harness.elements['file-search-progress'].textContent, /C:\\Users\\Test\\Documents/);

  await harness.pollFileSearch();
  assert.equal(harness.elements['file-search-submit'].disabled, false);
  assert.equal(harness.elements['file-search-cancel'].hidden, true);
  assert.equal(harness.elements['file-search-results'].items.length, 1);
  assert.equal(harness.elements['file-search-status'].textContent, '1 file found.');
});

test('chat file command runs local search and replies with matching paths', async () => {
  const harness = createSettingsHarness(
    { tracked_websites: [] },
    undefined,
    {
      start: async query => {
        assert.equal(query, 'resume');
        return 'chat-search';
      },
      getStatus: async () => ({
        status: 'completed',
        matches: [{ name: 'resume.pdf', path: 'C:\\Users\\Test\\resume.pdf' }],
        scanned_directories: 4,
        scanned_entries: 40,
        match_count: 1,
        skipped_directories: 0,
        skipped_items: 0,
        truncated: false,
        cancelled: false,
        current_path: ''
      })
    }
  );
  await new Promise(resolve => setImmediate(resolve));
  harness.elements['chat-input'].value = 'resume enga irukku?';

  await harness.listeners.chat({ preventDefault() {} });
  await harness.pollFileSearch();

  const replies = harness.elements['chat-messages'].children;
  assert.equal(replies[0].textContent, 'resume enga irukku?');
  assert.match(replies[1].textContent, /C:\\Users\\Test\\resume\.pdf/);
  assert.equal(harness.elements['file-name'].value, 'resume');
});

test('chat YouTube command saves the requested limit locally', async () => {
  let updated;
  const harness = createSettingsHarness(
    { tracked_websites: [] },
    undefined,
    {},
    {
      setWebsiteLimit: async (domain, minutes) => {
        updated = { domain, minutes };
        return { domain, limit_minutes: minutes };
      }
    }
  );
  await new Promise(resolve => setImmediate(resolve));
  harness.elements['chat-input'].value = 'YouTube limit 1 minute pannu';

  await harness.listeners.chat({ preventDefault() {} });

  assert.deepEqual(updated, { domain: 'youtube.com', minutes: 1 });
  assert.equal(harness.elements['youtube-limit'].value, 1);
  assert.match(harness.elements['chat-messages'].children[1].textContent, /1 minute-ku set panniten/);
});

test('chat answers live battery status from local system stats without calling the chat model', async () => {
  let statsRead = 0;
  let modelCalled = false;
  const harness = createSettingsHarness(
    { tracked_websites: [] },
    undefined,
    {},
    {
      getSystemStats: async () => {
        statsRead += 1;
        return { battery_percent: 63.4, is_plugged: false };
      },
      chatWithGemini: async () => {
        modelCalled = true;
        return 'I cannot inspect your laptop.';
      }
    }
  );
  await new Promise(resolve => setImmediate(resolve));
  harness.elements['chat-agent'].value = 'quick-chat';
  harness.elements['chat-input'].value = 'battery evvulavu iruku?';

  await harness.listeners.chat({ preventDefault() {} });

  assert.equal(statsRead, 1);
  assert.equal(modelCalled, false);
  assert.match(harness.elements['chat-messages'].lastChild.textContent, /battery 63% irukku; charger not connected/);
});

test('chat reports unavailable battery readings instead of making up a percentage', async () => {
  const harness = createSettingsHarness(
    { tracked_websites: [] },
    undefined,
    {},
    { getSystemStats: async () => ({ battery_percent: null, is_plugged: null }) }
  );
  await new Promise(resolve => setImmediate(resolve));
  harness.elements['chat-input'].value = 'Can you access real-time status?';

  await harness.listeners.chat({ preventDefault() {} });

  assert.match(harness.elements['chat-messages'].lastChild.textContent, /reading available illa/);
});

test('general chat uses Gemini and keeps only Gemini conversation context', async () => {
  const requests = [];
  const harness = createSettingsHarness(
    { tracked_websites: [] },
    undefined,
    {},
    {
      chatWithGemini: async (message, history) => {
        requests.push({ message, history: JSON.parse(JSON.stringify(history)) });
        return `Reply ${requests.length}`;
      }
    }
  );
  await new Promise(resolve => setImmediate(resolve));

  harness.elements['chat-agent'].value = 'quick-chat';
  harness.elements['chat-input'].value = 'Vanakkam ARAVI';
  await harness.listeners.chat({ preventDefault() {} });
  harness.elements['chat-input'].value = 'What did I just say?';
  await harness.listeners.chat({ preventDefault() {} });

  assert.deepEqual(requests[0], { message: 'Vanakkam ARAVI', history: [] });
  assert.deepEqual(requests[1], {
    message: 'What did I just say?',
    history: [
      { role: 'user', text: 'Vanakkam ARAVI' },
      { role: 'model', text: 'Reply 1' }
    ]
  });
  assert.equal(harness.elements['chat-messages'].children[1].textContent, 'Reply 1');
  assert.equal(harness.elements['chat-messages'].children[3].textContent, 'Reply 2');
});

test('Gemini request shows animated typing dots until its reply arrives', async () => {
  let resolveReply;
  const harness = createSettingsHarness(
    { tracked_websites: [] },
    undefined,
    {},
    {
      chatWithGemini: () => new Promise(resolve => {
        resolveReply = resolve;
      })
    }
  );
  await new Promise(resolve => setImmediate(resolve));
  harness.elements['chat-agent'].value = 'quick-chat';
  harness.elements['chat-input'].value = 'Hello ARAVI';

  const request = harness.listeners.chat({ preventDefault() {} });
  await new Promise(resolve => setImmediate(resolve));

  const indicator = harness.elements['chat-messages'].lastChild;
  assert.equal(indicator.className, 'chat-message assistant-message typing-indicator');
  assert.equal(indicator.attributes['aria-label'], 'Karupu is typing');
  assert.equal(indicator.children.length, 3);
  assert.match(settingsCss, /@keyframes typing-bounce/);

  resolveReply('Hello! How can I help?');
  await request;
  assert.equal(indicator.textContent, 'Hello! How can I help?');
  assert.equal(indicator.className, 'chat-message assistant-message');
});

test('local web-search replies display safe clickable source links', async () => {
  const harness = createSettingsHarness(
    { tracked_websites: [] },
    undefined,
    {},
    {
      chatWithLocalSearch: async () =>
        'The latest update is available.\n\nSources:\nOfficial site | https://example.com/news\nUnsafe link | javascript:alert(1)'
    }
  );
  await new Promise(resolve => setImmediate(resolve));
  harness.elements['chat-input'].value = 'What are the latest updates?';
  await harness.listeners.chat({ preventDefault() {} });

  const reply = harness.elements['chat-messages'].lastChild;
  assert.equal(reply.textContent, 'The latest update is available.');
  assert.equal(reply.children.length, 1);
  assert.equal(reply.children[0].children.length, 1);
  const [link] = reply.children[0].children[0].children;
  assert.equal(link.textContent, 'Official site');
  assert.equal(link.href, 'https://example.com/news');
  assert.equal(link.target, '_blank');
  assert.equal(link.rel, 'noopener noreferrer');
});

test('chat agent selector passes web-search preference to Gemini', async () => {
  const requests = [];
  const harness = createSettingsHarness(
    { tracked_websites: [] },
    undefined,
    {},
    {
      chatWithGemini: async (...args) => {
        requests.push([args[0], JSON.parse(JSON.stringify(args[1])), args[2]]);
        return 'Agent reply';
      }
    }
  );
  await new Promise(resolve => setImmediate(resolve));
  harness.elements['chat-agent'].value = 'quick-chat';
  harness.elements['chat-input'].value = 'Explain gravity';
  await harness.listeners.chat({ preventDefault() {} });

  assert.equal(requests.length, 1);
  assert.equal(requests[0][0], 'Explain gravity');
  assert.deepEqual(requests[0][1], []);
  assert.equal(requests[0][2], false);
});

test('web-search agent uses local Ollama with separate history', async () => {
  const webRequests = [];
  let geminiCalled = false;
  const harness = createSettingsHarness(
    { tracked_websites: [] },
    undefined,
    {},
    {
      chatWithGemini: async () => {
        geminiCalled = true;
        return 'Cloud reply';
      },
      chatWithLocalSearch: async (...args) => {
        webRequests.push([args[0], JSON.parse(JSON.stringify(args[1]))]);
        return 'Local web answer.\n\nSources:\nSource | https://example.com';
      }
    }
  );
  await new Promise(resolve => setImmediate(resolve));
  harness.listeners.chatAgentChange();
  assert.equal(harness.elements['chat-agent-badge'].textContent, '● Ollama + Tavily Search');
  harness.elements['chat-input'].value = 'What are today headlines?';
  await harness.listeners.chat({ preventDefault() {} });

  assert.equal(geminiCalled, false);
  assert.equal(webRequests.length, 1);
  assert.deepEqual(webRequests[0], ['What are today headlines?', []]);
});

test('chat displays structured Gemini API errors without treating them as replies', async () => {
  const harness = createSettingsHarness(
    { tracked_websites: [] },
    undefined,
    {},
    {
      chatWithGemini: async () => ({ error: 'Gemini quota exceeded.' })
    }
  );
  await new Promise(resolve => setImmediate(resolve));
  harness.elements['chat-agent'].value = 'quick-chat';
  harness.elements['chat-input'].value = 'Explain gravity';
  await harness.listeners.chat({ preventDefault() {} });

  assert.equal(
    harness.elements['chat-messages'].lastChild.textContent,
    'Karupu (Gemini) error: Gemini quota exceeded.'
  );
});

test('chat labels missing Tavily configuration as a web-search error', async () => {
  const harness = createSettingsHarness(
    { tracked_websites: [] },
    undefined,
    {},
    {
      chatWithLocalSearch: async () => ({
        error: 'Web Search is not configured. Set the TAVILY_API_KEY Windows environment variable, then restart ARAVI.'
      })
    }
  );
  await new Promise(resolve => setImmediate(resolve));
  harness.elements['chat-agent'].value = 'web-search';
  harness.elements['chat-input'].value = 'Tell me about the latest news';
  await harness.listeners.chat({ preventDefault() {} });

  assert.equal(
    harness.elements['chat-messages'].lastChild.textContent,
    'Karupu Web Search (Ollama) error: Web Search is not configured. Set the TAVILY_API_KEY Windows environment variable, then restart ARAVI.'
  );
});

test('local Ollama agent uses separate local conversation history', async () => {
  const localRequests = [];
  const geminiRequests = [];
  const harness = createSettingsHarness(
    { tracked_websites: [] },
    undefined,
    {},
    {
      chatWithGemini: async (...args) => {
        geminiRequests.push(args);
        return 'Cloud reply';
      },
      chatWithLocalModel: async (...args) => {
        localRequests.push([args[0], JSON.parse(JSON.stringify(args[1]))]);
        return 'Local reply';
      }
    }
  );
  await new Promise(resolve => setImmediate(resolve));
  harness.elements['chat-agent'].value = 'local-ollama';
  harness.listeners.chatAgentChange();
  assert.equal(harness.elements['chat-agent-badge'].textContent, '● Local Ollama');

  harness.elements['chat-input'].value = 'Keep this local';
  await harness.listeners.chat({ preventDefault() {} });
  harness.elements['chat-input'].value = 'Continue locally';
  await harness.listeners.chat({ preventDefault() {} });

  assert.equal(localRequests.length, 2);
  assert.deepEqual(localRequests[0], ['Keep this local', []]);
  assert.deepEqual(localRequests[1], [
    'Continue locally',
    [
      { role: 'user', text: 'Keep this local' },
      { role: 'model', text: 'Local reply' }
    ]
  ]);
  assert.equal(geminiRequests.length, 0);
});

test('OpenCode agent uses its own conversation history', async () => {
  const requests = [];
  const harness = createSettingsHarness(
    { tracked_websites: [] },
    undefined,
    {},
    {
      chatWithOpenCode: async (message, history) => {
        requests.push({ message, history: JSON.parse(JSON.stringify(history)) });
        return `OpenCode reply ${requests.length}`;
      }
    }
  );
  await new Promise(resolve => setImmediate(resolve));
  harness.elements['chat-agent'].value = 'opencode';
  harness.listeners.chatAgentChange();
  assert.equal(harness.elements['chat-agent-badge'].textContent, '✦ Karupu + OpenCode');

  harness.elements['chat-input'].value = 'Hello';
  await harness.listeners.chat({ preventDefault() {} });
  harness.elements['chat-input'].value = 'Continue';
  await harness.listeners.chat({ preventDefault() {} });

  assert.deepEqual(requests, [
    { message: 'Hello', history: [] },
    {
      message: 'Continue',
      history: [
        { role: 'user', text: 'Hello' },
        { role: 'model', text: 'OpenCode reply 1' }
      ]
    }
  ]);
});

test('chat YouTube command requires an explicit time-limit intent', async () => {
  let cloudCalled = false;
  const harness = createSettingsHarness(
    { tracked_websites: [] },
    undefined,
    {},
    {
      chatWithGemini: async () => {
        cloudCalled = true;
        return 'General answer';
      }
    }
  );
  await new Promise(resolve => setImmediate(resolve));
  harness.elements['chat-agent'].value = 'quick-chat';
  harness.elements['chat-input'].value = 'I watched YouTube for 1 minute';

  await harness.listeners.chat({ preventDefault() {} });

  assert.equal(cloudCalled, true);
});
