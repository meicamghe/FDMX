# GNS Downloader Browser Extension — Privacy Notice

Last updated: 2026-11-26

## What the extension handles

To provide download handoff, the extension can inspect:
- The URL of a link when the user clicks a recognized file link or chooses **Download with GDM**.
- The URL of a browser download that the user starts.
- The URL and type of an HTML audio/video source on the current page.
- The current YouTube video URL and the available format labels returned by the locally installed GNS Downloader application.

## Where the information goes

Download and media URLs are sent to the GNS Downloader desktop application through a loopback-only HTTP bridge at `127.0.0.1:38471`, or through the registered `gnsdownloader://` operating-system protocol. The desktop application uses the URL to start the download and may keep the original URL in the user's local task/history records.

The extension does not send browsing URLs, page content, media metadata, or download history to a GNS-operated cloud service. It does not upload page contents or browsing history to an analytics service.

## GitHub sign-in

For GitHub Actions artifact links, the extension can request GitHub's redirect using the browser's existing signed-in session. The browser attaches its own GitHub session to the GitHub request. The extension does not read, export, log, or store cookie values. A short-lived signed artifact URL may be passed to the local desktop application for that download.

## Storage and retention

The extension does not persist browsing history or downloaded URLs in extension storage. The desktop application may retain download task and history information locally according to the application's own settings and user actions.

## Permissions

- `downloads`: detect browser downloads and hand them to GNS Downloader.
- `contextMenus`: add the **Download with GDM** right-click action.
- `tabs` / `activeTab`: access the current tab URL when the user invokes the extension.
- `notifications`: report a completed handoff.
- `<all_urls>`: detect file links and HTML audio/video elements on websites.
- `http://127.0.0.1:38471/*`: communicate with the local desktop application.
- GitHub host permissions: resolve authenticated GitHub Actions artifact redirects.

Firefox declares `websiteActivity` because the URL of a selected page/download/media item is handed from the extension to the local desktop application. This is local device-to-device application communication, not a remote upload.

## User control

The extension does not silently download media from a page. YouTube and page-media panels wait for the user's choice. Ordinary browser file downloads are automatically transferred after the user starts the download; if the desktop application cannot accept the handoff, the browser download is resumed.

You can disable or remove the extension from your browser's extension manager at any time.
