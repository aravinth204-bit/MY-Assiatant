const form = document.getElementById('limit-form');
const limitInput = document.getElementById('limit-minutes');
const playbackStatus = document.getElementById('playback-status');
const usageTime = document.getElementById('usage-time');
const warningStatus = document.getElementById('warning-status');
const message = document.getElementById('message');
const resetButton = document.getElementById('reset-button');

function formatDuration(seconds) {
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return minutes > 0
    ? `${minutes} min ${remainingSeconds} sec`
    : `${remainingSeconds} sec`;
}

async function sendRequest(request) {
  const response = await chrome.runtime.sendMessage(request);
  if (!response || !response.ok) {
    throw new Error(response && response.error ? response.error : 'ARAVI extension did not respond.');
  }
  return response.result;
}

async function refreshStatus() {
  try {
    const status = await sendRequest({ type: 'get-status' });
    limitInput.value = status.limitMinutes;
    usageTime.textContent = formatDuration(status.usageSeconds);
    playbackStatus.textContent = status.isPlaying
      ? 'YouTube video is playing. Playback is being counted.'
      : 'No YouTube video is currently playing.';
    warningStatus.textContent = status.warning
      ? 'The limit warning is active; the YouTube tab will close shortly.'
      : '';
    warningStatus.classList.toggle('hidden', !status.warning);
  } catch (error) {
    message.textContent = error.message;
  }
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  message.textContent = '';
  try {
    await sendRequest({
      type: 'set-limit',
      minutes: Number(limitInput.value)
    });
    message.textContent = 'Limit saved.';
    await refreshStatus();
  } catch (error) {
    message.textContent = error.message;
  }
});

resetButton.addEventListener('click', async () => {
  message.textContent = '';
  try {
    await sendRequest({ type: 'reset-usage' });
    message.textContent = 'Today’s playback timer was reset.';
    await refreshStatus();
  } catch (error) {
    message.textContent = error.message;
  }
});

void refreshStatus();
