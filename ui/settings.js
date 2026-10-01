const SITE_DEFAULTS = [
  { domain: 'youtube.com', inputId: 'youtube-limit', fallback: 30 },
  { domain: 'instagram.com', inputId: 'instagram-limit', fallback: 20 }
];

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('limits-form').addEventListener('submit', saveLimits);
  loadLimits();
});

function getSite(domain, sites) {
  return sites.find(site => site.domain.toLowerCase().includes(domain));
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
    const existingSites = config.tracked_websites || [];
    config.tracked_websites = SITE_DEFAULTS.map(site => {
      const previous = getSite(site.domain, existingSites);
      return {
        domain: site.domain,
        limit_minutes: Number(document.getElementById(site.inputId).value),
        used_seconds: previous ? previous.used_seconds || 0 : 0
      };
    });
    const saved = await window.pywebview.api.save_config(config);
    status.textContent = saved ? 'Limits saved.' : 'Could not save limits.';
  } catch (error) {
    status.textContent = 'Could not save limits.';
  }
}
