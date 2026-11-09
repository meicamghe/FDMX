# FDMX Browser Extensions

Firefox and Chrome extensions for sending HTTP/HTTPS URLs to the FDMX desktop application.

## Desktop requirement
Use the updated FDMX desktop app containing the local browser bridge. It listens only on 127.0.0.1:38471. The bridge accepts requests only from browser-extension origins and validates HTTP/HTTPS URLs.

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
The folders are source distributions. ZIP them for Chrome "Load unpacked" workflow and package the Firefox folder as an XPI for temporary/testing installation. An unsigned XPI cannot be permanently installed in standard Firefox release builds; submit/sign through addons.mozilla.org for that.
