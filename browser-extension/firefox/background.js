browser.runtime.onInstalled.addListener(() => {
  browser.contextMenus.create({id:"send-link-to-fdmx",title:"Download link with GNS Downloader",contexts:["link"]});
});
browser.contextMenus.onClicked.addListener(async(info) => {
  if(info.menuItemId !== "send-link-to-fdmx" || !info.linkUrl) return;
  const saved = await browser.storage.local.get("fdmxToken");
  if(!saved.fdmxToken) return;
  try{
    await fetch("http://127.0.0.1:47831/add",{
      method:"POST",
      headers:{"Content-Type":"application/json","Authorization":"Bearer "+saved.fdmxToken},
      body:JSON.stringify({url:info.linkUrl})
    });
  }catch(_error){}
});