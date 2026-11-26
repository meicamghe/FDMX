(() => {
  if (window.__gnsDownloaderMediaUI) return;
  window.__gnsDownloaderMediaUI = true;

  const runtime = chrome.runtime;
  const isYouTube = /(^|\.)youtube\.com$|(^|\.)youtu\.be$/i.test(location.hostname);
  const directUrl = value => {
    if (!value) return "";
    try {
      const url = new URL(value, location.href);
      return /^https?:$/.test(url.protocol) ? url.href : "";
    } catch (_) { return ""; }
  };

  function request(message) {
    return new Promise(resolve => {
      try {
        runtime.sendMessage(message, response => {
          if (chrome.runtime.lastError) resolve({ok: false, error: chrome.runtime.lastError.message});
          else resolve(response || {ok: false, error: "No response from GNS Downloader"});
        });
      } catch (error) { resolve({ok: false, error: error.message}); }
    });
  }

  function buildPanel() {
    const host = document.createElement("div");
    host.id = "gns-downloader-media-panel";
    host.style.cssText = "position:fixed;right:22px;bottom:22px;z-index:2147483647;";
    const shadow = host.attachShadow({mode: "closed"});
    shadow.innerHTML = `
      <style>
        .card{width:300px;box-sizing:border-box;padding:14px;border-radius:12px;background:#17191f;color:#f5f5f5;font:13px/1.45 Arial,sans-serif;box-shadow:0 8px 30px #0008;border:1px solid #454852}
        .head{display:flex;align-items:center;gap:9px;margin-bottom:8px;font-size:14px;font-weight:700}
        .mark{width:24px;height:24px;border-radius:6px;background:#fff;color:#e2231a;display:grid;place-items:center;font:bold 20px Arial}
        p{margin:5px 0 10px;color:#c8ccd5}.actions{display:flex;gap:7px;margin-top:10px}
        button,select{font:inherit;border-radius:7px;padding:8px;border:1px solid #626775}
        button{background:#bd1825;color:white;font-weight:700;cursor:pointer;flex:1}
        button.secondary{background:#30343d;color:#eee}.close{background:transparent;border:0;color:#aaa;padding:0 4px;flex:none}
        select{width:100%;background:#242832;color:white}
        .status{font-size:12px;color:#c8ccd5;min-height:17px;margin-top:8px}
      </style>
      <div class="card">
        <div class="head"><span class="mark">G</span><span>GNS Downloader</span><button class="close" title="Close">×</button></div>
        <p class="message"></p>
        <div class="choices"></div>
        <div class="status"></div>
      </div>`;
    shadow.querySelector(".close").addEventListener("click", () => host.remove());
    document.documentElement.appendChild(host);
    return {host, shadow};
  }

  async function showYouTubePanel() {
    if (document.getElementById("gns-downloader-media-panel")) return;
    const {host, shadow} = buildPanel();
    shadow.querySelector(".message").textContent = "Finding available video qualities and audio…";
    shadow.querySelector(".status").textContent = "Checking with GNS Downloader";
    const response = await request({type: "GNS_YOUTUBE_FORMATS", url: location.href});
    if (!host.isConnected) return;
    if (!response || !response.ok) {
      shadow.querySelector(".message").textContent = "YouTube media detected.";
      shadow.querySelector(".status").textContent = response && response.error ? response.error : "Open GNS Downloader 6.53 or newer.";
      return;
    }
    shadow.querySelector(".message").textContent = response.title || "Choose a YouTube download format";
    const choices = shadow.querySelector(".choices");
    const select = document.createElement("select");
    select.setAttribute("aria-label", "Download format");
    for (const quality of (response.qualities || [{label:"Best available",height:0}])) {
      const option = document.createElement("option");
      option.value = "video:" + Number(quality.height || 0);
      option.textContent = "Video · " + quality.label;
      select.appendChild(option);
    }
    if (response.audio_available !== false) {
      const audioQualities = response.audio_qualities || [{label:"Best audio",bitrate:0}];
      for (const quality of audioQualities) {
        const option = document.createElement("option");
        option.value = "audio:0:" + Number(quality.bitrate || 0);
        option.textContent = "Audio only · " + quality.label;
        select.appendChild(option);
      }
    }
    choices.appendChild(select);
    const actions = document.createElement("div");
    actions.className = "actions";
    const download = document.createElement("button");
    download.textContent = "Download with GNS";
    download.addEventListener("click", async () => {
      const [mediaType, height, audioBitrate] = select.value.split(":");
      download.disabled = true;
      shadow.querySelector(".status").textContent = "Sending to GNS Downloader…";
      const result = await request({
        type: "GNS_YOUTUBE_DOWNLOAD", url: location.href,
        media_type: mediaType, height: Number(height || 0), audio_bitrate: Number(audioBitrate || 0)
      });
      shadow.querySelector(".status").textContent = result && result.ok
        ? "Added to the GNS Downloader queue."
        : (result && result.error) || "Could not start the download.";
      download.disabled = false;
    });
    const dismiss = document.createElement("button");
    dismiss.className = "secondary";
    dismiss.textContent = "Not now";
    dismiss.addEventListener("click", () => host.remove());
    actions.append(download, dismiss);
    choices.appendChild(actions);
    shadow.querySelector(".status").textContent = "Select video quality or audio only.";
  }

  function findDirectMedia() {
    const media = Array.from(document.querySelectorAll("video,audio"));
    for (const element of media) {
      const candidates = [element.currentSrc, element.src, ...Array.from(element.querySelectorAll("source"), node => node.src)];
      const url = candidates.map(directUrl).find(Boolean);
      if (url) return {url, type: element.tagName.toLowerCase()};
    }
    return null;
  }

  async function showDirectMediaPanel(found) {
    if (!found || document.getElementById("gns-downloader-media-panel")) return;
    const {host, shadow} = buildPanel();
    shadow.querySelector(".message").textContent = (found.type === "audio" ? "Audio" : "Video") + " media detected on this page.";
    const choices = shadow.querySelector(".choices");
    const actions = document.createElement("div");
    actions.className = "actions";
    const download = document.createElement("button");
    download.textContent = "Download with GNS";
    download.addEventListener("click", async () => {
      download.disabled = true;
      shadow.querySelector(".status").textContent = "Sending media to GNS Downloader…";
      const result = await request({type:"GNS_SEND_URL",url:found.url});
      shadow.querySelector(".status").textContent = result && result.ok
        ? "Added to the GNS Downloader queue."
        : (result && result.error) || "Could not start the download.";
      download.disabled = false;
    });
    const dismiss = document.createElement("button");
    dismiss.className = "secondary";
    dismiss.textContent = "Not now";
    dismiss.addEventListener("click", () => host.remove());
    actions.append(download, dismiss);
    choices.appendChild(actions);
    shadow.querySelector(".status").textContent = "The media URL is sent only after you choose Download.";
  }

  function detect() {
    if (isYouTube && /\/(watch|shorts|live)(\/|$)/.test(location.pathname)) {
      showYouTubePanel();
      return;
    }
    const media = findDirectMedia();
    if (media) showDirectMediaPanel(media);
  }


  const downloadExtensions = /\.(?:7z|apk|avi|csv|deb|dmg|docx?|exe|flac|gz|iso|m4a|mkv|mov|mp3|mp4|msi|pdf|png|pptx?|rar|rpm|tar|wav|webm|xlsx?|zip)$/i;
  document.addEventListener("click", event => {
    if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const anchor = event.target && event.target.closest ? event.target.closest("a[href]") : null;
    if (!anchor) return;
    const url = directUrl(anchor.href);
    if (!url) return;
    let path = "";
    try { path = new URL(url).pathname; } catch (_) { return; }
    if (!anchor.hasAttribute("download") && !downloadExtensions.test(path)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    request({type: "GNS_SEND_URL", url}).then(result => {
      if (!result || !result.ok) {
        console.warn("GNS Downloader could not take over this link; returning to the browser.", result && result.error);
        window.location.assign(url);
      }
    });
  }, true);

  detect();
  const observer = new MutationObserver(() => detect());
  observer.observe(document.documentElement, {childList:true,subtree:true});
  window.addEventListener("yt-navigate-finish", () => {
    const panel = document.getElementById("gns-downloader-media-panel");
    if (panel) panel.remove();
    detect();
  });
})();
