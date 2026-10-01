let currentPose = 'idle';
let animationTimer = null;
let bubbleHideTimer = null;
let walkFrame = 1;

let isPointerDown = false;
let isDraggingMascot = false;
let startScreenX = 0;
let startScreenY = 0;
let isMovingWindow = false;

const SPRITES = {
  idle: ['assets/sprites/Idle.png?v=2', 'assets/sprites/Idle Blink.png?v=2'],
  walk: ['assets/sprites/Walk Step 1.png?v=2', 'assets/sprites/Walk Step 2.png?v=2'],
  sit: ['assets/sprites/Sit.png?v=2'],
  webshoot: ['assets/sprites/Web-Shoot.png?v=2'],
  tired: ['assets/sprites/Tired.png?v=2'],
  alert: ['assets/sprites/Tired.png?v=2'],
  celebrate: ['assets/sprites/Celebrate.png?v=2']
};

document.addEventListener('DOMContentLoaded', () => {
  setPose('idle');
  setInterval(checkSystemStatus, 5000);
  setupMascotDragAndClick();
});

function setupMascotDragAndClick() {
  const mascotEl = document.getElementById('mascot');
  if (!mascotEl) return;

  let lastClickTime = 0;
  let totalMoveDistance = 0;
  let downScreenX = 0;
  let downScreenY = 0;

  const onPointerDown = (e) => {
    if (e.button !== 0) return;
    isPointerDown = true;
    isDraggingMascot = false;
    totalMoveDistance = 0;
    downScreenX = e.screenX;
    downScreenY = e.screenY;
    startScreenX = e.screenX;
    startScreenY = e.screenY;

    try {
      if (mascotEl.setPointerCapture) {
        mascotEl.setPointerCapture(e.pointerId);
      }
    } catch (err) {}
  };

  const onPointerMove = (e) => {
    if (!isPointerDown) return;
    
    const dx = e.screenX - startScreenX;
    const dy = e.screenY - startScreenY;
    const totalDistFromStart = Math.hypot(e.screenX - downScreenX, e.screenY - downScreenY);
    totalMoveDistance = Math.max(totalMoveDistance, totalDistFromStart);

    // Threshold of 5px to engage dragging
    if (totalMoveDistance >= 5) {
      isDraggingMascot = true;
      mascotEl.style.cursor = 'grabbing';
      startScreenX = e.screenX;
      startScreenY = e.screenY;

      if (!isMovingWindow) {
        isMovingWindow = true;
        if (window.pywebview && window.pywebview.api && window.pywebview.api.move_window_by) {
          window.pywebview.api.move_window_by(dx, dy).finally(() => {
            isMovingWindow = false;
          });
        } else {
          isMovingWindow = false;
        }
      }
    }
  };

  const onPointerUp = (e) => {
    if (!isPointerDown) return;
    isPointerDown = false;
    mascotEl.style.cursor = 'grab';

    try {
      if (mascotEl.releasePointerCapture) {
        mascotEl.releasePointerCapture(e.pointerId);
      }
    } catch (err) {}

    const now = Date.now();
    // If movement was below 5px threshold, treat as a stationary click
    if (!isDraggingMascot && totalMoveDistance < 5) {
      const timeSinceLastClick = now - lastClickTime;
      if (timeSinceLastClick > 0 && timeSinceLastClick < 400) {
        // DOUBLE CLICK: open Control Center
        openControlCenter(e);
        lastClickTime = 0;
      } else {
        // Single click: record time, trigger small notice animation
        lastClickTime = now;
        mascotEl.style.transform = 'scale(0.95)';
        setTimeout(() => {
          mascotEl.style.transform = '';
        }, 150);
      }
    } else {
      // Was a drag, reset double click tracker
      lastClickTime = 0;
    }

    isDraggingMascot = false;
    totalMoveDistance = 0;
  };

  mascotEl.addEventListener('pointerdown', onPointerDown);
  mascotEl.addEventListener('pointermove', onPointerMove);
  mascotEl.addEventListener('pointerup', onPointerUp);
  mascotEl.addEventListener('pointercancel', onPointerUp);

  // Fallback for mouse events if pointer events are not triggered
  mascotEl.addEventListener('mousedown', onPointerDown);
  window.addEventListener('mousemove', onPointerMove);
  window.addEventListener('mouseup', onPointerUp);
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

  if (pose === 'idle') {
    imgElement.classList.add('idle-pose');
    let isBlinking = false;
    animationTimer = setInterval(() => {
      isBlinking = !isBlinking && Math.random() > 0.6;
      imgElement.src = isBlinking ? SPRITES.idle[1] : SPRITES.idle[0];
    }, 1500);
  } 
  else if (pose === 'walk') {
    imgElement.classList.add('walk-pose');
    animationTimer = setInterval(() => {
      walkFrame = (walkFrame === 1) ? 2 : 1;
      imgElement.src = SPRITES.walk[walkFrame - 1];
    }, 300);
  } 
  else if (pose === 'webshoot') {
    imgElement.src = SPRITES.webshoot[0];
    webLine.classList.remove('hidden');
    setTimeout(() => {
      webLine.classList.add('hidden');
      setPose('idle');
    }, 2000);
  } 
  else if (pose === 'celebrate') {
    imgElement.classList.add('celebrate-pose');
    imgElement.src = SPRITES.celebrate[0];
    setTimeout(() => {
      setPose('idle');
    }, 2500);
  } 
  else {
    imgElement.src = (SPRITES[pose] && SPRITES[pose][0]) ? SPRITES[pose][0] : SPRITES.idle[0];
  }

  if (message) {
    showSpeechBubble(message);
  }
}

function showSpeechBubble(text, durationMs = 5000) {
  const bubble = document.getElementById('speech-bubble');
  const textEl = document.getElementById('speech-text');
  
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
function canNotify(key, cooldownMs = 300000) { // default 5 minutes (300,000 ms)
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
window.showSpeechBubble = showSpeechBubble;
window.openControlCenter = openControlCenter;

