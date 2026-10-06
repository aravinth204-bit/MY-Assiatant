const SITE_DEFAULTS = [
  { domain: 'youtube.com', inputId: 'youtube-limit', fallback: 30 },
  { domain: 'instagram.com', inputId: 'instagram-limit', fallback: 20 }
];

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('limits-form').addEventListener('submit', saveLimits);
  document.getElementById('observation-toggle').addEventListener('click', toggleObservation);
  loadLimits();
  loadObservationStatus();
});

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
