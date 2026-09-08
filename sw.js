const CACHE="ters-kose-v2-shell-8";
const CORE=["./","./manifest.json","./icon.svg"];

self.addEventListener("install",e=>{
  e.waitUntil(caches.open(CACHE).then(c=>c.addAll(CORE)));
  self.skipWaiting()
});

self.addEventListener("activate",e=>{
  e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))));
  self.clients.claim()
});

self.addEventListener("fetch",e=>{
  if(e.request.method!=="GET")return;
  const u=new URL(e.request.url);

  // Large/live football datasets must stay network-only. Caching these files
  // caused stale bulletins and unnecessary storage/memory pressure on iPhone.
  if(u.origin===self.location.origin && u.pathname.includes("/data/")){
    e.respondWith(fetch(e.request,{cache:"no-store"}));
    return
  }
  if(u.pathname.startsWith("/proxy"))return;

  // Shell assets: network first, cached fallback for offline launch.
  e.respondWith(
    fetch(e.request).then(r=>{
      if(r && (r.ok || r.type==="opaque")){
        const copy=r.clone();
        caches.open(CACHE).then(c=>c.put(e.request,copy)).catch(()=>{})
      }
      return r
    }).catch(()=>caches.match(e.request).then(r=>r||caches.match("./")))
  )
});
