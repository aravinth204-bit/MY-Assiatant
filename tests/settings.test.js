const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const settingsSource = fs.readFileSync(
  path.join(__dirname, '..', 'ui', 'settings.js'),
  'utf8'
);

function createSettingsHarness(config, fileSearch = async () => ({
  matches: [],
  skipped_directories: 0,
  skipped_items: 0,
  truncated: false
}), searchApi = {}, chatApi = {}) {
  const listeners = {};
  let intervalCallback;
  const elements = {
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
    'chat-send': { disabled: false },
    'chat-connection-status': { textContent: '' },
    'chat-messages': {
      children: [{ textContent: 'Vanakkam! File thedanuma, illa YouTube limit maathanuma?' }],
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
    'save-status': { textContent: '' },
    'observation-status': { textContent: '' },
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
      createElement: tagName => ({
        tagName,
        children: [],
        className: '',
        append(...children) {
          this.children.push(...children);
        },
        textContent: ''
      })
    },
    window: {
      pywebview: {
        api: {
          get_config: async () => JSON.parse(JSON.stringify(config)),
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
          get_chat_status: chatApi.getChatStatus || (async () => ({
            gemini_configured: true
          })),
          chat_with_gemini: chatApi.chatWithGemini || (async () => 'Vanakkam!'),
          get_window_observation_status: async () => observationActive,
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
          intervalCallback = callback;
          return 1;
        },
        clearInterval() {
          intervalCallback = null;
        }
      }
    },
    setInterval(callback) {
      intervalCallback = callback;
      return 1;
    },
    clearInterval() {
      intervalCallback = null;
    }
  };

  vm.runInNewContext(settingsSource, context);
  listeners.domContentLoaded();

  return {
    elements,
    listeners,
    getSavedConfig: () => savedConfig,
    async pollFileSearch() {
      await intervalCallback();
    }
  };
}

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

test('activity observation can be started and stopped explicitly', async () => {
  const harness = createSettingsHarness({ tracked_websites: [] });
  await new Promise(resolve => setImmediate(resolve));

  assert.equal(harness.elements['observation-status'].textContent, 'Observation is off.');
  assert.equal(harness.elements['observation-toggle'].textContent, 'Start observing');

  await harness.listeners.observationToggle();
  assert.equal(harness.elements['observation-status'].textContent, 'Observation is on. Active window titles are shown by ARAVI.');
  assert.equal(harness.elements['observation-toggle'].textContent, 'Stop observing');

  await harness.listeners.observationToggle();
  assert.equal(harness.elements['observation-status'].textContent, 'Observation is off.');
  assert.equal(harness.elements['observation-toggle'].textContent, 'Start observing');
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
  assert.equal(replies[1].textContent, 'resume enga irukku?');
  assert.match(replies[2].textContent, /C:\\Users\\Test\\resume\.pdf/);
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
  assert.match(harness.elements['chat-messages'].children[2].textContent, /1 minute-ku set panniten/);
});

test('general chat uses Gemini and keeps only Gemini conversation context', async () => {
  const requests = [];
  const harness = createSettingsHarness(
    { tracked_websites: [] },
    undefined,
    {},
    {
      getChatStatus: async () => ({ gemini_configured: true }),
      chatWithGemini: async (message, history) => {
        requests.push({ message, history: JSON.parse(JSON.stringify(history)) });
        return `Reply ${requests.length}`;
      }
    }
  );
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(
    harness.elements['chat-connection-status'].textContent,
    'Gemini is ready. General chat messages are sent to Google.'
  );

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
  assert.equal(harness.elements['chat-messages'].children[2].textContent, 'Reply 1');
  assert.equal(harness.elements['chat-messages'].children[4].textContent, 'Reply 2');
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
  harness.elements['chat-input'].value = 'I watched YouTube for 1 minute';

  await harness.listeners.chat({ preventDefault() {} });

  assert.equal(cloudCalled, true);
});

test('Gemini setup status clearly reports when the API key is missing', async () => {
  const harness = createSettingsHarness(
    { tracked_websites: [] },
    undefined,
    {},
    { getChatStatus: async () => ({ gemini_configured: false }) }
  );
  await new Promise(resolve => setImmediate(resolve));

  assert.match(
    harness.elements['chat-connection-status'].textContent,
    /GEMINI_API_KEY.*restart ARAVI/
  );
});
