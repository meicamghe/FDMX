const API = "http://127.0.0.1:38471";
const MENU_LINK = "gns-download-link";
const MENU_PAGE = "gns-download-page";
const MENU_SELECTION = "gns-download-selection";

async function resolveUrl(url) {
  let resolvedUrl = "";
  try {
    const result = await fdmxResolveBrowserAuthenticatedUrl(url);
    if (result && result.browserSession) resolvedUrl = result.url;
  } catch (error) {
    console.warn("GNS Downloader GitHub session resolution:", error);
  }
  return resolvedUrl;
}

async function postToGNS(path, payload) {
  let response;
  try {
    response = await fetch(API + path, {
      method: "POST",
      headers: {"Content-Type": "text/plain;charset=UTF-8"},
      body: JSON.stringify(payload)
    });
  } catch (error) {
    error.bridgeUnavailable = true;
    throw error;
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    const error = new Error(data.error || "GNS Downloader rejected the request");
    error.bridgeUnavailable = false;
    throw error;
  }
  return data;
}

async function sendToGNS(url) {
  if (!url || !/^https?:\/\//i.test(url)) return {ok: false, resolvedUrl: ""};
  const resolvedUrl = await resolveUrl(url);
  try {
    await postToGNS("/download", {url, resolved_url: resolvedUrl});
    return {ok: true, resolvedUrl};
  } catch (error) {
    console.warn("GNS Downloader local bridge:", error);
    return {ok: false, resolvedUrl, bridgeUnavailable: !!error.bridgeUnavailable};
  }
}

function protocolUrl(action, values) {
  const target = new URL("gnsdownloader://" + action);
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== null && value !== "") target.searchParams.set(key, String(value));
  }
  return target.href;
}

async function launchGNS(url, resolvedUrl = "") {
  if (!url || !/^https?:\/\//i.test(url)) return false;
  try {
    await chrome.tabs.create({
      url: protocolUrl("download", {url, resolved_url: resolvedUrl}),
      active: false
    });
    return true;
  } catch (error) {
    console.warn("GNS Downloader protocol launch failed:", error);
    return false;
  }
}

async function waitForGNS(timeoutMs = 6000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(API + "/health", {cache: "no-store"});
      if (response.ok) return true;
    } catch (_) {}
    await new Promise(resolve => setTimeout(resolve, 400));
  }
  return false;
}

async function sendOrLaunch(url) {
  const result = await sendToGNS(url);
  if (result.ok) return true;
  if (!result.bridgeUnavailable) return false;
  const launched = await launchGNS(url, result.resolvedUrl);
  return launched && await waitForGNS();
}

function createMenus() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: MENU_LINK,
      title: "Download with GDM",
      contexts: ["link", "image", "video", "audio"]
    });
    chrome.contextMenus.create({
      id: MENU_PAGE,
      title: "Send page to GNS Downloader",
      contexts: ["page"]
    });
    chrome.contextMenus.create({
      id: MENU_SELECTION,
      title: "Download selected URL with GNS Downloader",
      contexts: ["selection"]
    });
  });
}

if (chrome.runtime.getManifest().manifest_version === 3) {
  chrome.runtime.onInstalled.addListener(createMenus);
} else {
  createMenus();
}

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === MENU_LINK) sendOrLaunch(info.linkUrl || info.srcUrl);
  if (info.menuItemId === MENU_PAGE) sendOrLaunch(info.pageUrl || (tab && tab.url));
  if (info.menuItemId === MENU_SELECTION) sendOrLaunch((info.selectionText || "").trim());
});

chrome.downloads.onCreated.addListener(async item => {
  if (!item || item.id === undefined || !/^https?:\/\//i.test(item.url || "")) return;
  if (item.byExtension) return;
  let paused = false;
  try {
    await chrome.downloads.pause(item.id);
    paused = true;
  } catch (_) {
    // Some downloads cannot be paused immediately; do not cancel until handoff succeeds.
  }

  const result = await sendToGNS(item.url);
  let handedOff = result.ok;
  if (!handedOff && result.bridgeUnavailable) {
    const launched = await launchGNS(item.url, result.resolvedUrl);
    handedOff = launched && await waitForGNS();
  }

  if (handedOff) {
    try { await chrome.downloads.cancel(item.id); } catch (_) {}
    try {
      await chrome.notifications.create("gns-auto-" + item.id, {
        type: "basic",
        iconUrl: "icons/gns-downloader-128.png",
        title: "GNS Downloader",
        message: "Download transferred to GNS Downloader."
      });
    } catch (_) {}
  } else if (paused) {
    try { await chrome.downloads.resume(item.id); } catch (_) {}
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || !message.type) return false;
  if (message.type === "GNS_SEND_URL") {
    sendOrLaunch(message.url).then(ok => sendResponse({ok})).catch(error => sendResponse({ok: false, error: error.message}));
    return true;
  }
  if (message.type === "GNS_YOUTUBE_FORMATS") {
    postToGNS("/youtube/formats", {url: message.url})
      .then(data => sendResponse(data))
      .catch(async error => {
        if (!error.bridgeUnavailable) {
          sendResponse({ok: false, error: error.message});
          return;
        }
        try {
          await chrome.tabs.create({url: "gnsdownloader://open", active: false});
          sendResponse({ok: false, error: "GNS Downloader is starting. Please retry format detection in a moment."});
        } catch (_) {
          sendResponse({ok: false, error: error.message});
        }
      });
    return true;
  }
  if (message.type === "GNS_YOUTUBE_DOWNLOAD") {
    const payload = {
      url: message.url,
      media_type: message.media_type,
      height: message.height || 0,
      audio_bitrate: message.audio_bitrate || 0
    };
    postToGNS("/youtube/download", payload)
      .then(data => sendResponse(data))
      .catch(error => {
        if (!error.bridgeUnavailable) {
          sendResponse({ok: false, error: error.message});
          return;
        }
        // The app can also be started through the registered desktop protocol.
        const target = protocolUrl("youtube", payload);
        chrome.tabs.create({url: target, active: false})
          .then(() => sendResponse({ok: true, launched: true}))
          .catch(() => sendResponse({ok: false, error: error.message}));
      });
    return true;
  }
  return false;
});
