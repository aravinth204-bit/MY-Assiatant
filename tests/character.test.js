const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const characterSource = fs.readFileSync(
  path.join(__dirname, '..', 'ui', 'character.js'),
  'utf8'
);
const characterStyles = fs.readFileSync(
  path.join(__dirname, '..', 'ui', 'character.css'),
  'utf8'
);

function createCharacterHarness() {
  const classes = () => {
    const values = new Set();
    return {
      add: value => values.add(value),
      remove: value => values.delete(value),
      contains: value => values.has(value)
    };
  };
  let onDOMContentLoaded;
  const timeouts = [];
  const intervals = new Map();
  let nextIntervalId = 0;
  const speechBubbleClasses = classes();
  speechBubbleClasses.add('hidden');
  const elements = {
    'app-container': { classList: classes() },
    'speech-bubble': { classList: speechBubbleClasses, addEventListener() {} },
    'warning-site': { textContent: '' },
    'warning-countdown': { textContent: '' },
    'warning-seconds': { textContent: '' },
    'speech-text': { innerText: '' },
    'sprite-img': { className: '', src: '', style: {} },
    'web-line': { className: '' },
    mascot: { addEventListener() {}, style: {} }
  };
  const context = {
    document: {
      addEventListener(event, callback) {
        if (event === 'DOMContentLoaded') onDOMContentLoaded = callback;
      },
      getElementById: id => elements[id]
    },
    window: { addEventListener() {} },
    setTimeout: (callback, durationMs) => {
      timeouts.push({ callback, durationMs });
      return timeouts.length;
    },
    clearTimeout() {},
    setInterval: callback => {
      const id = ++nextIntervalId;
      intervals.set(id, callback);
      return id;
    },
    clearInterval: id => intervals.delete(id)
  };

  vm.runInNewContext(characterSource, context);
  return {
    elements,
    intervals,
    timeouts,
    tickIntervals() {
      for (const callback of [...intervals.values()]) callback();
    },
    window: context.window,
    onDOMContentLoaded
  };
}

test('startup plays frames 1-4 before showing the ARAVI greeting', () => {
  const { elements, intervals, onDOMContentLoaded, tickIntervals, timeouts } = createCharacterHarness();

  onDOMContentLoaded();

  assert.equal(elements['sprite-img'].src, 'assets/character-frames/ezgif-frame-001.png');
  assert.equal(elements['speech-bubble'].classList.contains('hidden'), true);
  tickIntervals();
  tickIntervals();
  tickIntervals();
  assert.equal(elements['sprite-img'].src, 'assets/character-frames/ezgif-frame-004.png');
  tickIntervals();
  assert.equal(intervals.size, 0);
  assert.equal(elements['speech-text'].innerText, 'Hi, I am ARAVI, your personal assistant.');
  assert.equal(elements['speech-bubble'].classList.contains('hidden'), false);
  assert.equal(timeouts.at(-1).durationMs, 5000);
  timeouts.at(-1).callback();
  assert.equal(elements['speech-bubble'].classList.contains('hidden'), true);
});

test('speech bubble is positioned above the mascot with a readable background', () => {
  const bubbleStyles = characterStyles.match(/\.speech-bubble \{([^}]+)\}/)[1];

  assert.match(bubbleStyles, /top:\s*12px/);
  assert.match(bubbleStyles, /background:\s*rgba\(15,\s*23,\s*42,\s*0\.96\)/);
  assert.match(bubbleStyles, /box-shadow:/);
});

test('roaming poses use the exact supplied frame ranges', () => {
  const { elements, tickIntervals, window } = createCharacterHarness();

  for (const [pose, firstFrame, lastFrame] of [
    ['walk_right', 5, 13],
    ['climb_up', 15, 22],
    ['ceiling_walk', 25, 31],
    ['climb_down', 33, 35],
    ['landing', 36, 40]
  ]) {
    window.setPose(pose);
    assert.equal(
      elements['sprite-img'].src,
      `assets/character-frames/ezgif-frame-${String(firstFrame).padStart(3, '0')}.png`
    );
    assert.equal(elements['sprite-img'].style.transform, '');
    for (let frame = firstFrame; frame < lastFrame; frame += 1) {
      tickIntervals();
    }
    assert.equal(
      elements['sprite-img'].src,
      `assets/character-frames/ezgif-frame-${String(lastFrame).padStart(3, '0')}.png`
    );
    if (pose === 'landing') tickIntervals();
  }
});

test('time-limit warning remains visible when another speech message arrives', () => {
  const { elements, window } = createCharacterHarness();

  window.showTimeLimitWarning('youtube.com', 10);
  window.showSpeechBubble('System status update');

  assert.equal(elements['app-container'].classList.contains('time-warning-mode'), true);
  assert.equal(elements['speech-bubble'].classList.contains('hidden'), false);
  assert.equal(elements['warning-site'].textContent, 'YouTube');
  assert.equal(elements['warning-countdown'].textContent, 10);
  assert.equal(elements['speech-text'].innerText, '');
});

test('hiding the time-limit warning restores the normal mascot state', () => {
  const { elements, window } = createCharacterHarness();

  window.showTimeLimitWarning('youtube.com', 10);
  window.hideTimeLimitWarning();

  assert.equal(elements['app-container'].classList.contains('time-warning-mode'), false);
  assert.equal(elements['speech-bubble'].classList.contains('hidden'), true);
});
