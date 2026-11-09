const api = typeof browser !== "undefined" ? browser : chrome;
const tokenField = document.getElementById("token");
const statusBox = document.getElementById("status");
async function loadToken(){const saved=await api.storage.local.get("fdmxToken");tokenField.value=saved.fdmxToken||"";}
async function sendUrl(url){
 const token=tokenField.value.trim();if(!token){statusBox.textContent="Paste and save the token from FDMX first.";return;}
 try{const response=await fetch("http://127.0.0.1:47831/add",{method:"POST",headers:{"Content-Type":"application/json","Authorization":"Bearer "+token},body:JSON.stringify({url})});
 const result=await response.json();if(!response.ok)throw new Error(result.error||"Bridge rejected the request");statusBox.textContent="Sent to GNS Downloader.";
 }catch(error){statusBox.textContent="Could not connect. Open FDMX and check the token. "+error.message;}
}
document.getElementById("save").addEventListener("click",async()=>{await api.storage.local.set({fdmxToken:tokenField.value.trim()});statusBox.textContent="Token saved.";});
document.getElementById("send").addEventListener("click",async()=>{const tabs=await api.tabs.query({active:true,currentWindow:true});if(tabs[0]&&tabs[0].url)await sendUrl(tabs[0].url);else statusBox.textContent="No active page URL found.";});
loadToken();