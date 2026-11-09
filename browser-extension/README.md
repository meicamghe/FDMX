# GNS Downloader browser connector — v6.3

## What it does
- Popup button sends the current tab URL to the running GNS Downloader.
- Right-click a link and choose **Download link with GNS Downloader**.
- Supports HTTP, HTTPS, and magnet links.

## First-time setup
1. Start GNS Downloader v6.3.
2. In the left menu, open **Browser extension**.
3. Copy the security token.
4. Load the extension folder for your browser:
   - Chrome: open `chrome://extensions`, enable Developer mode, choose **Load unpacked**, and select `browser-extension/chrome`.
   - Firefox: open `about:debugging#/runtime/this-firefox`, choose **Load Temporary Add-on**, and select `browser-extension/firefox/manifest.json`.
5. Open the extension popup, paste the token, and click **Save token**.

The app listens only on `127.0.0.1:47831`. Requests require the app-generated bearer token. Keep the token private.
