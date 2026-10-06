# ARAVI YouTube Time Limit

This Chrome extension counts actual YouTube video playback, including playback in a background tab. When the daily limit is reached, Chrome shows a notification and closes that YouTube tab after a 10-second warning.

Playback status and usage stay in Chrome's local extension storage. The extension does not capture screenshots or send browsing data to a server.

## Install in Chrome

1. Open `chrome://extensions` in Chrome.
2. Turn on **Developer mode**.
3. Select **Load unpacked**.
4. Choose this `chrome-extension` folder.
5. Pin **ARAVI YouTube Time Limit** from Chrome's Extensions menu if you want quick access.
6. Open the extension popup and set the daily playback limit. The default is 30 minutes.

Set the limit in the extension popup; it is currently separate from the website limits in the ARAVI desktop app.

## Behavior

- Only YouTube videos that are actually playing are counted; a paused video does not accrue time.
- Usage is shared across YouTube tabs and resets at local midnight.
- At the limit, Chrome displays a notification and closes the YouTube tab that reached the limit after 10 seconds.
- **Reset today** clears the playback time and any active warning.
- Removing or disabling the extension stops tracking.
