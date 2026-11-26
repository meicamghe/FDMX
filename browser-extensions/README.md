# GNS Downloader Browser Extensions 1.2.0

Official Chrome and Firefox companion extensions for **GNS Downloader 6.52 or newer**.

## What's new in 1.2.0

- Correct product name: GNS Downloader (no FDMX branding in the browser UI).
- Matching app icon: white rounded square with the red G mark used by the desktop application.
- Firefox context menu is registered idempotently on install/update and browser startup; right-click a link, image, video, or audio item and choose **Download with GNS Downloader**.
- Automatic download handoff prompt: when Firefox or Chrome starts an HTTP/HTTPS file download, the extension offers **Download with GNS** or **Keep in browser**. Choosing GNS cancels the browser transfer and submits the original URL to the desktop app. Dismissing the prompt keeps/resumes the browser download.
- Existing signed-in GitHub Actions artifact resolution remains supported. Browser cookies are never read, exported, logged, or persisted.

## Desktop requirement

Run GNS Downloader 6.52 or newer. The local bridge listens only on `127.0.0.1:38471`.

## Firefox Developer Edition

1. Open `about:debugging#/runtime/this-firefox`.
2. Choose **Load Temporary Add-on**.
3. Select `GNS-Downloader-Firefox-1.2.0.xpi`.

Temporary installation is removed when Firefox closes. If this add-on already has an approved AMO listing, submit this XPI as an update to the same listing and keep the existing Gecko add-on ID; do not create a new listing or change the ID.

## Chrome

1. Extract `GNS-Downloader-Chrome-1.2.0.zip`.
2. Open `chrome://extensions` and enable Developer mode.
3. Choose **Load unpacked** and select the extracted folder.

## Automatic file-download prompt

The extension listens to the browser's downloads API. For HTTP/HTTPS downloads it pauses the browser transfer where supported and shows a notification with two choices:

- **Download with GNS** — cancel the browser transfer and send the URL to GNS Downloader.
- **Keep in browser** — resume/continue the normal browser download.

If the notification is dismissed or times out, the extension resumes any still-active browser download. The extension does not intercept ordinary page navigation, and it cannot hand off browser-only `blob:` or `data:` URLs.

## GitHub Actions browser-session support

For GitHub Actions artifact links, the extension resolves the authenticated GitHub redirect from the browser background context using the browser's own session. It never reads, exports, or stores session cookies. Only the short-lived signed download URL is passed to the local desktop bridge; the original GitHub URL remains the task/history URL.

## Privacy and permissions

The extension uses the browser downloads and notifications APIs to offer download handoff. GitHub session cookies are not accessed directly. The desktop bridge accepts requests only on loopback and validates HTTP/HTTPS URLs.

## Packaging

GitHub Actions creates versioned Chrome ZIP and Firefox XPI packages. An unsigned XPI can be loaded temporarily in Firefox Developer Edition; for a permanent standard Firefox installation, submit the update to addons.mozilla.org for signing.
