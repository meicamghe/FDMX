const API = "http://127.0.0.1:38471";

function sendToFDMX(value) {
  let url;
  try { url = new URL(value); } catch { return; }
  if (url.protocol !== "http:" && url.protocol !== "https:") return;
  fetch(API + "/download", {
    method: "POST",
    headers: {"Content-Type": "text/plain;charset=UTF-8"},
    body: JSON.stringify({url: url.href})
  }).then(async response => {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "FDMX is not responding");
  }).catch(error => console.warn("FDMX bridge:", error));
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({id: "fdmx-link", title: "Download link with FDMX", contexts: ["link"]});
    chrome.contextMenus.create({id: "fdmx-page", title: "Send page to FDMX", contexts: ["page"]});
    chrome.contextMenus.create({id: "fdmx-selection", title: "Send selected URL to FDMX", contexts: ["selection"]});
  });
});
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "fdmx-link") sendToFDMX(info.linkUrl);
  if (info.menuItemId === "fdmx-page") sendToFDMX(info.pageUrl || (tab && tab.url));
  if (info.menuItemId === "fdmx-selection") sendToFDMX((info.selectionText || "").trim());
});
chrome.runtime.onMessage.addListener(message => {
  if (message && message.type === "FDMX_DOWNLOAD") sendToFDMX(message.url);
});