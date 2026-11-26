# GNS Downloader Browser Extensions 1.3.0

Official Chrome and Firefox companion extensions for **GNS Downloader 6.53 or newer**.

## What's new in 1.3.0

- Uses the GNS Downloader name and the matching red G application icon.
- Right-click links, images, audio, or video and choose **Download with GDM**.
- Normal HTTP/HTTPS browser downloads are automatically handed to GNS Downloader. The extension pauses the browser transfer, submits the URL to the desktop app, then cancels the browser copy only after the desktop app accepts the request.
- If the desktop app is closed, the extension invokes the registered `gnsdownloader://` desktop protocol. The new app instance queues the URL and starts the download. If the app does not become available, the extension resumes the browser download instead.
- Pages with directly addressable audio/video elements show a small GNS media panel and wait for the user's choice.
- YouTube pages query the app's `yt-dlp` engine for available video heights and audio availability. The user can select a video quality or audio-only before queueing.
- GitHub Actions artifacts continue to use the browser's signed-in session. Cookies are never read, exported, logged, or persisted.

## Desktop requirement

Install **GNS Downloader 6.53 or newer**. This version registers the `gnsdownloader://` URL protocol and exposes a loopback-only bridge on `127.0.0.1:38471`.

The first time a browser opens the external `gnsdownloader://` protocol, the browser or operating system may ask permission to open GNS Downloader. Approve that one-time prompt.

## Firefox

The existing approved Mozilla Add-ons listing is:

https://addons.mozilla.org/en-US/firefox/addon/gns-download-manager/

The Gecko ID remains `fdmx-browser@gns.local`, so version 1.3.0 must be submitted as an update to that existing AMO listing, not as a new add-on. The current public listing is version 1.0.0; upload the new XPI from the successful 1.3.0 build and complete Mozilla review/signing.

For temporary testing in Firefox Developer Edition:
1. Open `about:debugging#/runtime/this-firefox`.
2. Choose **Load Temporary Add-on**.
3. Select `GNS-Downloader-Firefox-1.3.0.xpi`.

Temporary add-ons are removed when Firefox closes.

## Chrome — load unpacked

1. Open the [GNS Downloader browser-extension build workflow](https://github.com/meicamghe/FDMX/actions/workflows/build-browser-extensions.yml).
2. Open the latest successful run on the feature branch or main.
3. Under **Artifacts**, download `GNS-Downloader-browser-extensions-1.3.0`.
4. Extract the downloaded artifact ZIP.
5. Extract `GNS-Downloader-Chrome-1.3.0.zip` into a normal folder.
6. Open `chrome://extensions`.
7. Turn on **Developer mode**.
8. Click **Load unpacked** and select the extracted Chrome extension folder (the folder containing `manifest.json`).

Keep that folder in place; Chrome loads the unpacked extension from it. To update, extract the newer Chrome ZIP to a new folder, remove the old unpacked extension, then load the new folder.

For a public one-click Chrome installation, the extension must be submitted to the Chrome Web Store and pass its review. Until then, Developer mode is the supported installation method.

## Automatic downloads and privacy

The extension hands off HTTP/HTTPS downloads that the browser exposes through its downloads API. It does not silently read page cookies or transmit browsing history. Direct media URLs are sent to the local GNS bridge only after the user chooses the media panel action. YouTube format metadata is requested from the desktop app, and the selected media type/quality is sent back to the app.

The browser bridge binds only to loopback. Do not expose port 38471 to the LAN or Internet. Browser page content is inspected locally to detect media elements; it is not uploaded to a remote service.

## Limitations

- Browser-only `blob:` URLs and DRM-protected media cannot be passed as ordinary direct downloads.
- Some sites expose segmented or encrypted streams rather than a direct media URL. Detection may identify the player without being able to retrieve the media.
- YouTube format availability depends on the installed `yt-dlp` version, network access, and the video's restrictions. FFmpeg is needed to merge separate best-quality video and audio streams; without it, the app selects a compatible single-file stream at or below the chosen height.
- A browser may require a one-time confirmation before launching an external desktop protocol handler.

## Packaging

GitHub Actions validates scripts/manifests, renders the matching GNS icon sizes, and produces the Chrome ZIP and Firefox XPI as a versioned artifact.
