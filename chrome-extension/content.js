(() => {
  if (globalThis.__araviYoutubeTrackerInstalled) return;
  globalThis.__araviYoutubeTrackerInstalled = true;

  function reportPlayback() {
    const videos = document.querySelectorAll('video');
    const isPlaying = Array.from(videos).some(video =>
      !video.paused && !video.ended && video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA
    );
    chrome.runtime.sendMessage({
      type: 'youtube-playback',
      isPlaying
    }).catch(() => {});
  }

  function watchVideo(video) {
    for (const eventName of ['play', 'playing', 'pause', 'ended', 'emptied']) {
      video.addEventListener(eventName, reportPlayback);
    }
  }

  function findVideos() {
    document.querySelectorAll('video').forEach(watchVideo);
    reportPlayback();
  }

  findVideos();
  new MutationObserver(findVideos).observe(document.documentElement, {
    childList: true,
    subtree: true
  });
  setInterval(reportPlayback, 5000);
})();
