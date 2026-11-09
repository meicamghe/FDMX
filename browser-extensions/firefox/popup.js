const API="http://127.0.0.1:38471";
const status=document.getElementById("status");
async function send(url){
 if(!url || !/^https?:\\/\\//i.test(url)){status.textContent="No supported HTTP/HTTPS URL found.";return;}
 try{const r=await fetch(API+"/download",{method:"POST",headers:{"Content-Type":"text/plain;charset=UTF-8"},body:JSON.stringify({url})});const d=await r.json();if(!r.ok)throw new Error(d.error||"FDMX error");status.textContent="✓ Added to FDMX queue";}
 catch(e){status.textContent="Cannot connect to FDMX. Open the desktop app first. "+e.message;}
}
document.getElementById("current").addEventListener("click",async()=>{const [tab]=await chrome.tabs.query({active:true,currentWindow:true});send(tab&&tab.url);});
document.getElementById("video").addEventListener("click",async()=>{
 const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
 if(!tab||!tab.id){status.textContent="No active tab.";return;}
 try{const results=await chrome.scripting.executeScript({target:{tabId:tab.id},func:()=>Array.from(document.querySelectorAll("video, source")).map(x=>x.currentSrc||x.src).filter(x=>/^https?:/.test(x))});
 const urls=[...new Set((results[0]&&results[0].result)||[])];if(!urls.length){status.textContent="No direct video URL found on this page.";return;}for(const url of urls) await send(url);status.textContent="Sent "+urls.length+" media URL(s) to FDMX.";
 }catch(e){status.textContent="This page does not allow media inspection.";}
});