/* Radar ranking model: runs away from the iPhone main thread. */
self.onmessage=function(event){
  const items=(event.data&&event.data.items)||[];
  const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
  const scores=items.map(x=>{
    const resultMax=Math.max(x.p1,x.px,x.p2),marketMax=Math.max(x.btts,1-x.btts,x.o25,1-x.o25);
    const patternMax=Math.max(x.p12,x.p21,x.p6,x.engineStrength||0),sample=Math.min(1,(x.homeSample+x.awaySample)/30);
    const agreement=(resultMax-.333)*.9+(marketMax-.5)*.55;
    const consensusBoost=Math.min(.12,x.consensusCount*.018+x.consensusAverage*.035)*clamp(x.reliability||.5,.45,1);
    const radar=clamp(.36+.27*agreement+.17*x.confidence+.09*sample+.06*Math.min(1,patternMax*3)+consensusBoost,.35,.95);
    return clamp(radar*(.82+.18*x.completeness)*(x.trust>=.68?1:x.trust>=.56?.96:.90),.30,.95)
  });
  self.postMessage({scores:scores})
};
