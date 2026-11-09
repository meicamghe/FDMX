chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({id:"send-link-to-fdmx",title:"Download link with GNS Downloader",contexts:["link"]});
});
chrome.contextMenus.onClicked.addListener(async(info) => {
  if(info.menuItemId !== "send-link-to-fdmx" || !info.linkUrl) return;
  const saved = await chrome.storage.local.get("fdmxToken");
  if(!saved.fdmxToken) return;
  try{
    await fetch("http://127.0.0.1:47831/add",{
      method:"POST",
      headers:{"Content-Type":"application/json","Authorization":"Bearer "+saved.fdmxToken},
      body:JSON.stringify({url:info.linkUrl})
    });
  }catch(_error){}
});