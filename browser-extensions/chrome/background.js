const API = "http://127.0.0.1:38471";
const MENU_LINK = "gns-download-link";
const MENU_PAGE = "gns-download-page";
const MENU_SELECTION = "gns-download-selection";

async function sendToGNS(url) {
  if (!url || !/^https?:\/\//i.test(url)) return false;
  try {
    let resolved = {url, browserSession: false};
    try { resolved = await fdmxResolveBrowserAuthenticatedUrl(url); }
    catch (error) { console.warn("GitHub browser-session resolution:", error); }
    const response = await fetch(API + "/download", {
      method: "POST",
      headers: {"Content-Type": "text/plain;charset=UTF-8"},
      body: JSON.stringify({url, resolved_url: resolved.browserSession ? resolved.url : ""})
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "GNS Downloader is not responding");
    return true;
  } catch (error) {
    console.warn("GNS Downloader bridge:", error);
    try {
      await chrome.notifications.create("gns-bridge-error", {
        type: "basic", iconUrl: "icons/gns-downloader-128.png",
        title: "GNS Downloader", message: "Could not connect. Open GNS Downloader and try again."
      });
    } catch (_) {}
    return false;
  }
}

function createMenus() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: MENU_LINK, title: "Download link with GNS Downloader",
      contexts: ["link", "image", "video", "audio"]
    });
    chrome.contextMenus.create({
      id: MENU_PAGE, title: "Send page address to GNS Downloader", contexts: ["page"]
    });
    chrome.contextMenus.create({
      id: MENU_SELECTION, title: "Send selected URL to GNS Downloader", contexts: ["selection"]
    });
  });
}
chrome.runtime.onInstalled.addListener(createMenus);
chrome.runtime.onStartup.addListener(createMenus);

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === MENU_LINK) sendToGNS(info.linkUrl || info.srcUrl);
  if (info.menuItemId === MENU_PAGE) sendToGNS(info.pageUrl || (tab && tab.url));
  if (info.menuItemId === MENU_SELECTION) sendToGNS((info.selectionText || "").trim());
});
chrome.runtime.onMessage.addListener(message => {
  if (message && message.type === "GNS_DOWNLOAD") sendToGNS(message.url);
});

function isHttpDownload(item) {
  return !!(item && item.id !== undefined && /^https?:\/\//i.test(item.url || ""));
}
chrome.downloads.onCreated.addListener(async item => {
  if (!isHttpDownload(item)) return;
  const notificationId = "gns-download-" + item.id;
  try { await chrome.downloads.pause(item.id); } catch (_) {}
  const filename = (item.filename || item.url.split("/").pop() || "download").split(/[\\/]/).pop();
  try {
    await chrome.notifications.create(notificationId, {
      type: "basic",
      iconUrl: "icons/gns-downloader-128.png",
      title: "Download with GNS Downloader?",
      message: filename + " — choose GNS Downloader or keep the browser download.",
      buttons: [{title: "Download with GNS"}, {title: "Keep in browser"}],
      priority: 2
    });
  } catch (error) {
    console.warn("GNS download prompt:", error);
    try { await chrome.downloads.resume(item.id); } catch (_) {}
  }
});

async function handleDownloadChoice(notificationId, useGNS) {
  if (!notificationId.startsWith("gns-download-")) return;
  const id = Number(notificationId.slice("gns-download-".length));
  if (!Number.isInteger(id)) return;
  const items = await chrome.downloads.search({id});
  const item = items && items[0];
  if (!item) return;
  if (useGNS) {
    try { await chrome.downloads.cancel(id); } catch (_) {}
    await sendToGNS(item.url);
  } else {
    try { await chrome.downloads.resume(id); } catch (_) {}
  }
  try { await chrome.notifications.clear(notificationId); } catch (_) {}
}
chrome.notifications.onButtonClicked.addListener((id, index) => handleDownloadChoice(id, index === 0));
chrome.notifications.onClicked.addListener(id => handleDownloadChoice(id, true));
chrome.notifications.onClosed.addListener(id => {
  if (!id.startsWith("gns-download-")) return;
  const downloadId = Number(id.slice("gns-download-".length));
  if (!Number.isInteger(downloadId)) return;
  chrome.downloads.search({id: downloadId}).then(items => {
    if (items && items[0] && items[0].state === "in_progress") {
      return chrome.downloads.resume(downloadId);
    }
  }).catch(() => {});
});

// Reconcile context menus on background startup as well as install/update.
createMenus();
