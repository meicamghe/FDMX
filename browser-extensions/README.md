# FDMX Browser Extensions 1.1.0

Firefox and Chrome extensions for sending HTTP/HTTPS URLs to GNS Downloader 6.52 or newer.

## GitHub Actions browser-session support

For a GitHub Actions artifact link in the form `https://github.com/OWNER/REPO/actions/runs/RUN_ID/artifacts/ARTIFACT_ID`, the extension requests the artifact's download endpoint from the browser background context with `credentials: include`. The browser attaches its own GitHub session cookies; the extension never reads, exports, or stores those cookies. GitHub redirects the request to a short-lived signed object-storage URL, and only that URL is sent to the local desktop bridge. If the browser is not signed in or the artifact is unavailable, the extension falls back to the existing desktop authentication flow.

The signed download URL is temporary. Add the link to GNS Downloader immediately after the extension resolves it. The extension does not make private GitHub repositories public or bypass repository permissions.

## Desktop requirement
Use GNS Downloader 6.52 or newer containing the local browser bridge. It listens only on 127.0.0.1:38471. The bridge accepts requests only from browser-extension origins and validates HTTP/HTTPS URLs.

## Chrome
1. Open chrome://extensions
2. Enable Developer mode.
3. Choose Load unpacked.
4. Select the `chrome` folder.

## Firefox
1. Open about:debugging#/runtime/this-firefox
2. Choose Load Temporary Add-on.
3. Select `firefox/manifest.json`.
Temporary installation is removed when Firefox closes. Permanent installation requires Mozilla signing (AMO).

## Usage
Right-click a link and choose "Download link with FDMX", or open the extension popup to send the current page URL. The media scan button attempts to collect direct video/source URLs; DRM and streaming blob URLs are not downloadable this way.

## Packaging
The folders are source distributions. GitHub Actions creates versioned Chrome ZIP and Firefox XPI packages. An unsigned XPI cannot be permanently installed in standard Firefox release builds; submit/sign through addons.mozilla.org for that.

## Main project documentation

See the repository [README](../README.md) for project overview and [Persian setup guide](../docs/README_FA.md) for step-by-step installation and troubleshooting.
