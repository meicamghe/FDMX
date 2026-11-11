# Store listing — FDMX Download Manager

## Product name
FDMX Download Manager

## Short description
Send browser links and direct media URLs to the FDMX desktop download manager.

## Full description
FDMX Download Manager connects Chrome or Firefox to the FDMX desktop application.

Send the current page, a link, or a selected URL to your local FDMX download queue. You can also ask the extension to scan the active page for direct video and source URLs.

The extension communicates only with the FDMX desktop bridge running on your own computer at 127.0.0.1. It does not send browsing information to remote FDMX servers or advertising/analytics services.

Requires FDMX desktop version 6.40 or newer. DRM-protected streams and blob URLs may not be downloadable.

## Single purpose
Send a URL explicitly selected by the user from the browser to the locally installed FDMX desktop download manager.

## Privacy disclosure
The extension reads the current tab URL, a link URL, selected text, or direct media element URLs only after the user invokes the relevant command. The selected URL is sent to the local FDMX desktop application over 127.0.0.1; it is not sent to a remote service.

## Permission justifications
- contextMenus: adds the user-invoked link, page, and selection commands.
- activeTab: accesses the active page only after the user invokes the extension.
- tabs: reads the current tab URL for the send-current-page action.
- scripting: scans direct video/source elements only after the user presses the media scan button.
- host access to http://127.0.0.1:38471/*: sends selected URLs to the FDMX desktop bridge on the same device.

## Support
https://github.com/meicamghe/FDMX/issues

## Privacy policy
https://github.com/meicamghe/FDMX/blob/feature/browser-extension-store-publishing/browser-extensions/PRIVACY.md