# FDMX Download Manager — Privacy Policy

Last updated: 11 November 2026

FDMX Download Manager is a companion extension for the FDMX desktop application.

## What the extension accesses
The extension accesses a page URL, a link URL, selected text, or direct video/source URLs only after the user invokes an extension command. The media scan reads matching video and source elements on the active page only after the user presses the scan button.

## How information is used
The URL selected by the user is sent to the FDMX desktop application through a loopback connection to 127.0.0.1:38471. This connection stays on the user's device. The extension does not send browsing information to the FDMX developer, analytics providers, advertising networks, or other remote servers.

The extension does not maintain browsing history, build user profiles, or collect analytics.

## Permissions
- contextMenus — adds FDMX commands to the browser context menu.
- activeTab — allows access to the active page after the user invokes the extension.
- tabs — reads the active tab URL when the user requests it.
- scripting — scans direct media elements only after the user presses the media scan button.
- 127.0.0.1 host access — communicates with the locally running FDMX desktop bridge.

## Contact
For support, visit https://github.com/meicamghe/FDMX/issues.