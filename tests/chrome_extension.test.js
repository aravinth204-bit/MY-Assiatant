const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const extensionPath = path.join(__dirname, '..', 'chrome-extension');
const backgroundSource = fs.readFileSync(
  path.join(extensionPath, 'background.js'),
  'utf8'
);
const contentSource = fs.readFileSync(
  path.join(extensionPath, 'content.js'),
  'utf8'
);
const manifest = JSON.parse(fs.readFileSync(path.join(extensionPath, 'manifest.json'), 'utf8'));

function createEvent() {
  return {
    listeners: [],
    addListener(listener) {
      this.listeners.push(listener);
    }
  };
}

function createBackgroundHarness() {
  let now = new Date(2026, 9, 6, 12, 0, 0).getTime();
  let stored = {};
  let warningTimeoutCallback;
  const notifications = [];
  const closedTabs = [];
  const alarms = [];
  const messageEvent = createEvent();
  const alarmEvent = createEvent();

  class FakeDate extends Date {
    constructor(...args) {
      super(...(args.length ? args : [now]));
    }

    static now() {
      return now;
    }
  }

  const chrome = {
    storage: {
      local: {
        async get(defaults) {
          return { ...defaults, ...stored };
        },
        async set(values) {
          stored = { ...stored, ...values };
        }
      }
    },
    runtime: {
      onMessage: messageEvent,
      onInstalled: createEvent(),
      onStartup: createEvent(),
      getURL: path => `chrome-extension://aravi/${path}`
    },
    alarms: {
      onAlarm: alarmEvent,
      create: (name, info) => alarms.push({ name, info }),
      clear: async () => true
    },
    tabs: {
      onRemoved: createEvent(),
      query: async () => [],
      get: async id => ({ id, windowId: 1 }),
      update: async () => {},
      remove: async id => closedTabs.push(id)
    },
    windows: { update: async () => {} },
    notifications: {
      onClicked: createEvent(),
      create: async (...args) => notifications.push(args),
      clear: async () => true
    },
    scripting: { executeScript: async () => {} }
  };

  vm.runInNewContext(backgroundSource, {
    chrome,
    Date: FakeDate,
    console,
    setTimeout(callback) {
      warningTimeoutCallback = callback;
      return 1;
    },
    clearTimeout() {}
  });

  return {
    alarms,
    closedTabs,
    notifications,
    sendMessage(message, tabId = 7) {
      return new Promise((resolve, reject) => {
        const keepChannelOpen = messageEvent.listeners[0](
          message,
          { tab: { id: tabId } },
          resolve
        );
        if (!keepChannelOpen) reject(new Error('Message channel was not kept open.'));
      });
    },
    advanceTime(milliseconds) {
      now += milliseconds;
    },
    fireWarningTimeout() {
      assert.equal(typeof warningTimeoutCallback, 'function');
      warningTimeoutCallback();
    }
  };
}

test('extension manifest requests only playback tracking and tab-control permissions', () => {
  assert.equal(manifest.manifest_version, 3);
  assert.ok(manifest.permissions.includes('tabs'));
  assert.ok(manifest.permissions.includes('storage'));
  assert.ok(manifest.host_permissions.every(url =>
    url.includes('youtube.com') || url.includes('youtu.be')
  ));
  assert.equal(manifest.background.service_worker, 'background.js');
});

test('background playback is counted and closes its YouTube tab after warning', async () => {
  const harness = createBackgroundHarness();

  await harness.sendMessage({ type: 'set-limit', minutes: 1 });
  await harness.sendMessage({ type: 'youtube-playback', isPlaying: true });
  for (let heartbeat = 0; heartbeat < 12; heartbeat += 1) {
    harness.advanceTime(5000);
    await harness.sendMessage({ type: 'youtube-playback', isPlaying: true });
  }

  const status = await harness.sendMessage({ type: 'get-status' });
  assert.equal(status.result.usageSeconds, 60);
  assert.equal(status.result.warning.tabId, 7);
  assert.equal(harness.notifications.length, 1);
  assert.equal(harness.alarms.length, 1);

  harness.fireWarningTimeout();
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(harness.closedTabs, [7]);
});

test('content script reports actual video playback, independent of tab visibility', async () => {
  const events = {};
  const messages = [];
  const video = {
    paused: true,
    ended: false,
    readyState: 2,
    addEventListener(name, callback) {
      events[name] = callback;
    }
  };
  const context = {
    document: {
      documentElement: {},
      querySelectorAll: () => [video]
    },
    HTMLMediaElement: { HAVE_CURRENT_DATA: 2 },
    MutationObserver: class {
      observe() {}
    },
    chrome: {
      runtime: {
        sendMessage: message => {
          messages.push(message);
          return Promise.resolve();
        }
      }
    },
    setInterval() {},
    setTimeout,
    clearTimeout,
    console
  };

  vm.runInNewContext(contentSource, context);
  video.paused = false;
  events.playing();
  await new Promise(resolve => setImmediate(resolve));

  assert.equal(messages.at(-1).type, 'youtube-playback');
  assert.equal(messages.at(-1).isPlaying, true);
});
