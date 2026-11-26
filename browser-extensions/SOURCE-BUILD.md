# Mozilla AMO source submission — GNS Downloader Firefox 1.3.0

This source bundle contains the original, readable Firefox extension source and the build procedure used to create the submitted XPI. It also includes the matching Chrome source because both browser targets share the same implementation and icon artwork.

## Reproduction target

- Firefox add-on: **GNS Downloader**
- Version: **1.3.0**
- Gecko add-on ID: `fdmx-browser@gns.local`
- Output: `dist/GNS-Downloader-Firefox-1.3.0.xpi`

The XPI is made from the files under `firefox/`. The JavaScript, HTML, CSS and manifest are shipped as readable source; they are not transpiled, concatenated, minified or generated. The PNG icon sizes are build assets rendered from the supplied original SVG artwork.

## Build environment

Supported reference environment: Ubuntu 22.04 LTS or newer (64-bit).

Required tools:

| Tool | Version | Installation |
|---|---|---|
| Bash | 5.x (Ubuntu system Bash) | Included with Ubuntu |
| Python | 3.10+ | `sudo apt-get install python3` |
| Node.js | 18+ | Install the current Node.js 18 LTS or newer from the official Node.js distribution |
| librsvg | 2.x, providing `rsvg-convert` | `sudo apt-get install librsvg2-bin` |
| Info-ZIP | 3.x, providing `zip` | `sudo apt-get install zip` |

No npm packages or third-party JavaScript dependencies are required. Node.js is used only for syntax validation; it does not transform the source.

## Step-by-step reproduction

1. Extract this source archive to a writable directory.
2. Install the required Ubuntu packages:

   ```sh
   sudo apt-get update
   sudo apt-get install -y python3 nodejs librsvg2-bin zip
   ```

3. Confirm Node.js is version 18 or newer:

   ```sh
   node --version
   ```

4. Run the included build script:

   ```sh
   chmod +x build.sh
   ./build.sh
   ```

5. The script:
   - renders the 16, 32, 48 and 128 pixel PNG icons from each browser target's supplied `icons/gns-downloader.svg`;
   - validates the manifests and required generated icon files;
   - runs `node --check` against each original JavaScript file;
   - packages the Firefox source directory as an XPI and the Chrome source directory as a ZIP.

6. Find the reproduced Firefox add-on at:

   ```
   dist/GNS-Downloader-Firefox-1.3.0.xpi
   ```

   The Chrome package is also written to `dist/GNS-Downloader-Chrome-1.3.0.zip`.

To put build outputs somewhere else, pass an output directory, for example `./build.sh /tmp/gns-output`.

## Source layout

- `firefox/manifest.json` — Firefox add-on manifest, permissions and Gecko ID.
- `firefox/background.js` — browser events, download handoff and local desktop bridge.
- `firefox/github-auth.js` — GitHub artifact URL resolution through the browser's authenticated session; does not read or export cookies.
- `firefox/media-detect.js` — page media detection and user-facing media/YouTube panel.
- `firefox/popup.html`, `firefox/popup.js` — toolbar popup source.
- `firefox/icons/gns-downloader.svg` — original vector icon source.
- `firefox/icons/*.png` — rendered icon assets included in the extension package.
- `chrome/` — corresponding Chrome source and assets.
- `build.sh` — complete build and validation script.

## Notes for reviewers

- The extension source is intentionally kept readable and unminified.
- No webpack, bundler, transpiler, template engine, or JavaScript minifier is used.
- The only generated extension files are the PNG icon sizes, reproducibly rendered from the included SVG by `rsvg-convert`.
- The archive does not include the desktop application's source because it is a separately installed companion application; this archive builds the browser add-on itself.
