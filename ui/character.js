let currentPose = 'idle';
let animationTimer = null;
let bubbleHideTimer = null;
let orientationMode = 'normal';
let orientationDirection = 'right';

let isPointerDown = false;
let isDraggingMascot = false;
let startScreenX = 0;
let startScreenY = 0;
let isMovingWindow = false;

const FRAME_ASSETS = Array.from({ length: 40 }, (_, index) =>
  `assets/character-frames/ezgif-frame-${String(index + 1).padStart(3, '0')}.png`
);

document.addEventListener('DOMContentLoaded', () => {
  setPose('idle');
  setInterval(checkSystemStatus, 5000);
  setupMascotDragAndClick();
});

function setOrientation(mode, direction) {
  const mascotEl = document.getElementById('mascot');
  if (!mascotEl) return;

  orientationMode = mode;
  orientationDirection = direction;
  mascotEl.style.transform = '';
  const imgElement = document.getElementById('sprite-img');
  if (imgElement) {
    imgElement.style.transform = mode === 'upside_down' ? 'scaleX(-1)' : '';
  }
}

function triggerWebLine(direction) {
  const webLine = document.getElementById('web-line');
  if (!webLine) return;
  webLine.className = `web-line web-line-${direction}`;
}

function clearWebLine() {
  const webLine = document.getElementById('web-line');
  if (webLine) {
    webLine.className = 'web-line hidden';
  }
}

function showTimeLimitWarning(domain, secondsRemaining) {
  const app = document.getElementById('app-container');
  const bubble = document.getElementById('speech-bubble');
  if (!app || !bubble) return;

  if (animationTimer) {
    clearInterval(animationTimer);
    animationTimer = null;
  }
  if (bubbleHideTimer) {
    clearTimeout(bubbleHideTimer);
    bubbleHideTimer = null;
  }

  app.classList.add('time-warning-mode');
  bubble.classList.remove('hidden');
  document.getElementById('warning-site').textContent = domain.toLowerCase().includes('instagram') ? 'Instagram' : 'YouTube';
  document.getElementById('warning-countdown').textContent = secondsRemaining;
  document.getElementById('warning-seconds').textContent = secondsRemaining;
}

function hideTimeLimitWarning() {
  const app = document.getElementById('app-container');
  const bubble = document.getElementById('speech-bubble');
  if (app) app.classList.remove('time-warning-mode');
  if (bubble) bubble.classList.add('hidden');
  setPose('idle');
}

function setupMascotDragAndClick() {
  const mascotEl = document.getElementById('mascot');
  const speechEl = document.getElementById('speech-bubble');

  let isMouseDown = false;
  let hasDragged = false;
  let startX = 0;
  let startY = 0;
  let lastMoveX = 0;
  let lastMoveY = 0;

  const pauseRoaming = () => {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.pause_roaming) {
      window.pywebview.api.pause_roaming(20.0);
    }
  };

  if (speechEl) {
    speechEl.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      openControlCenter(e);
    });
  }

  const onPointerDown = (e) => {
    if (e.button !== undefined && e.button !== 0) return;

    pauseRoaming();
    isMouseDown = true;
    hasDragged = false;
    startX = e.screenX;
    startY = e.screenY;
    lastMoveX = e.screenX;
    lastMoveY = e.screenY;

    if (mascotEl) mascotEl.style.cursor = 'grabbing';
  };

  const onPointerMove = (e) => {
    if (!isMouseDown) return;

    const dx = e.screenX - lastMoveX;
    const dy = e.screenY - lastMoveY;
    const totalDist = Math.hypot(e.screenX - startX, e.screenY - startY);

    if (totalDist > 4) {
      hasDragged = true;
      lastMoveX = e.screenX;
      lastMoveY = e.screenY;

      if (!isMovingWindow && (dx !== 0 || dy !== 0)) {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.move_window_by) {
          isMovingWindow = true;
          window.pywebview.api.move_window_by(dx, dy).finally(() => {
            isMovingWindow = false;
          });
        }
      }
    }
  };

  const onPointerUp = (e) => {
    if (!isMouseDown) return;
    isMouseDown = false;
    if (mascotEl) mascotEl.style.cursor = 'grab';

    if (!hasDragged) {
      openControlCenter(e);
    }
    hasDragged = false;
  };

  if (mascotEl) {
    mascotEl.addEventListener('mousedown', onPointerDown);
    mascotEl.addEventListener('dblclick', (e) => {
      e.stopPropagation();
      openControlCenter(e);
    });

    window.addEventListener('mousemove', onPointerMove);
    window.addEventListener('mouseup', onPointerUp);

    mascotEl.addEventListener('touchstart', (e) => {
      if (e.touches && e.touches[0]) {
        onPointerDown({ button: 0, screenX: e.touches[0].screenX, screenY: e.touches[0].screenY });
      }
    });
    window.addEventListener('touchmove', (e) => {
      if (e.touches && e.touches[0]) {
        onPointerMove({ screenX: e.touches[0].screenX, screenY: e.touches[0].screenY });
      }
    });
    window.addEventListener('touchend', onPointerUp);
  }
}

function setPose(pose, message = null) {
  currentPose = pose;
  const imgElement = document.getElementById('sprite-img');
  const webLine = document.getElementById('web-line');
  
  if (animationTimer) {
    clearInterval(animationTimer);
    animationTimer = null;
  }

  imgElement.className = 'mascot-img';

  const playFrames = (frameNumbers, intervalMs = 120) => {
    let frameIndex = 0;
    imgElement.src = FRAME_ASSETS[frameNumbers[frameIndex] - 1];
    animationTimer = setInterval(() => {
      frameIndex = (frameIndex + 1) % frameNumbers.length;
      imgElement.src = FRAME_ASSETS[frameNumbers[frameIndex] - 1];
    }, intervalMs);
  };

  if (pose === 'idle') {
    imgElement.src = FRAME_ASSETS[39];
  } 
  else if (pose === 'walk') {
    const frameNumbers = orientationMode === 'upside_down'
      ? Array.from({ length: 9 }, (_, index) => 8 + index)
      : orientationDirection === 'left'
        ? [39, 40]
        : Array.from({ length: 9 }, (_, index) => 8 + index);
    playFrames(frameNumbers);
  } 
  else if (pose === 'webshoot') {
    const frameNumbers = orientationDirection === 'right'
      ? Array.from({ length: 8 }, (_, index) => 17 + index)
      : [39, 40];
    playFrames(frameNumbers);
  } 
  else if (pose === 'celebrate') {
    playFrames([1, 2, 3, 4, 5, 6, 7, 8], 140);
    setTimeout(() => {
      setPose('idle');
    }, 2500);
  } 
  else {
    imgElement.src = FRAME_ASSETS[39];
  }

  if (message) {
    showSpeechBubble(message);
  }
}

function showSpeechBubble(text, durationMs = 5000) {
  const bubble = document.getElementById('speech-bubble');
  const textEl = document.getElementById('speech-text');
  
  if (!text) return;
  textEl.innerText = text;
  bubble.classList.remove('hidden');

  if (bubbleHideTimer) {
    clearTimeout(bubbleHideTimer);
  }

  bubbleHideTimer = setTimeout(() => {
    bubble.classList.add('hidden');
  }, durationMs);
}

function openControlCenter(event) {
  if (event) event.stopPropagation();
  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.open_settings();
  }
}

const notificationCooldowns = {};
function canNotify(key, cooldownMs = 300000) {
  const now = Date.now();
  const last = notificationCooldowns[key] || 0;
  if (now - last >= cooldownMs) {
    notificationCooldowns[key] = now;
    return true;
  }
  return false;
}

function checkSystemStatus() {
  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.get_system_stats().then(stats => {
      if (stats.is_tired && currentPose !== 'tired') {
        if (canNotify('tired_warning', 300000)) {
          setPose('tired', 'Phew! System high load or low battery...');
        }
      } else if (stats.is_storage_alert && currentPose !== 'alert') {
        if (canNotify('storage_warning', 300000)) {
          setPose('alert', 'Warning: Free storage space is under 10%!');
        }
      }
    }).catch(err => console.log('Error checking stats:', err));
  }
}

window.setPose = setPose;
window.setOrientation = setOrientation;
window.triggerWebLine = triggerWebLine;
window.clearWebLine = clearWebLine;
window.showTimeLimitWarning = showTimeLimitWarning;
window.hideTimeLimitWarning = hideTimeLimitWarning;
window.showSpeechBubble = showSpeechBubble;
window.openControlCenter = openControlCenter;
