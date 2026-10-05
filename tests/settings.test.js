const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const settingsSource = fs.readFileSync(
  path.join(__dirname, '..', 'ui', 'settings.js'),
  'utf8'
);

function createSettingsHarness(config) {
  const listeners = {};
  const elements = {
    'limits-form': {
      addEventListener: (event, handler) => {
        listeners.submit = handler;
      }
    },
    'youtube-limit': { value: '15' },
    'instagram-limit': { value: '25' },
    'save-status': { textContent: '' }
  };
  let savedConfig;

  const context = {
    document: {
      addEventListener: (event, handler) => {
        listeners.domContentLoaded = handler;
      },
      getElementById: id => elements[id]
    },
    window: {
      pywebview: {
        api: {
          get_config: async () => JSON.parse(JSON.stringify(config)),
          save_config: async nextConfig => {
            savedConfig = nextConfig;
            return true;
          }
        }
      }
    }
  };

  vm.runInNewContext(settingsSource, context);
  listeners.domContentLoaded();

  return {
    elements,
    listeners,
    getSavedConfig: () => savedConfig
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
