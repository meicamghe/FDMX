# FDMX Browser Extensions

Chrome and Firefox companion extensions for sending user-selected HTTP/HTTPS links and direct media URLs to the FDMX desktop download manager.

## Requirements
- FDMX desktop version 6.40 or newer.
- The desktop application must be running. Its browser bridge listens only on 127.0.0.1:38471.
- The bridge accepts requests from browser extension origins and validates HTTP/HTTPS URLs.

## Features
- Send the current page to FDMX from the extension popup.
- Right-click a link and choose Download link with FDMX.
- Send a selected URL from the context menu.
- Scan the active page for direct video and source URLs after pressing the media scan button.

DRM-protected streams, encrypted media, and blob URLs are not converted into downloadable files by this extension.

## Development installation

### Chrome
1. Open chrome://extensions.
2. Enable Developer mode.
3. Choose Load unpacked.
4. Select browser-extensions/chrome.

### Firefox
1. Open about:debugging#/runtime/this-firefox.
2. Choose Load Temporary Add-on.
3. Select browser-extensions/firefox/manifest.json.

## Store submission packages
GitHub Actions creates:
- FDMX-Chrome-Web-Store.zip — upload this ZIP to the Chrome Web Store developer dashboard.
- FDMX-Firefox-AMO.zip — source package for AMO review and signing.
- FDMX-Firefox.xpi — installable package; a public Firefox release must be signed by Mozilla.

See STORE_LISTING.md for store listing text and permission justifications. The privacy policy is in PRIVACY.md.

## Notes
The extension does not communicate with remote FDMX servers. When the user explicitly invokes an action, it sends the selected URL to the local desktop application over loopback.

## Main project documentation
See the repository README and Persian setup guide at docs/README_FA.md.