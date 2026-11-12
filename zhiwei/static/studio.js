import {demoEdgeGeometry} from './graph-routing.js';
export const escapeHTML = s => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const e=escapeHTML;
export function dialog(title, body) {
 const el=document.createElement('dialog');el.className='studio-dialog';
 el.innerHTML=`<div class="row dialog-heading"><h2>${e(title)}</h2><button data-close aria-label="关闭窗口">关闭 ×</button></div>${body}`;
 document.body.append(el);el.querySelector('[data-close]').onclick=()=>el.close();
 el.addEventListener('close',()=>el.remove(),{once:true});el.showModal();return el;
}
export function mediaPreview(a) {
 return a.mime.startsWith('image/')?`<img loading="lazy" src="/v1/assets/${encodeURIComponent(a.id)}" alt="${e(a.name)}">`:`<video controls preload="metadata" src="/v1/assets/${encodeURIComponent(a.id)}" aria-label="${e(a.name)}"></video>`;
}
export function uploadMedia(course,file,name,onProgress=()=>{}) {
 return new Promise((resolve,reject)=>{
  if(file.size>30*1024*1024)return reject(Error('文件超过当前本地版 30 MB 限制'));
  const xhr=new XMLHttpRequest();xhr.open('POST',`/v1/courses/${course}/assets`);
  xhr.setRequestHeader('Content-Type',file.type);xhr.setRequestHeader('X-Filename',encodeURIComponent(name||file.name));
  xhr.upload.onprogress=event=>{if(event.lengthComputable)onProgress(Math.round(event.loaded/event.total*100));};
  xhr.onload=()=>{try{const d=JSON.parse(xhr.responseText);xhr.status>=200&&xhr.status<300?resolve(d):reject(Error(d.message||'上传失败'));}catch{reject(Error('上传响应无效'));}};
  xhr.onerror=()=>reject(Error('网络中断，请重新上传'));xhr.send(file);
 });
}
export async function pickMedia({course,kind,api,onChoose}) {
 const title=kind==='image'?'图片':kind==='video'?'视频':'素材';
 const el=dialog(`选择${title}`,`<p>直接上传后插入，或从课程素材库选择。文件上限 30 MB。</p><div class="upload-box"><label>素材名称（可用中文）<input id="upload-name" placeholder="选择文件后会填入文件名"></label><label>选择本地${title}<input id="direct-upload" type="file" accept="${kind==='image'?'image/png,image/jpeg':kind==='video'?'video/mp4':'image/png,image/jpeg,video/mp4'}"></label><button id="upload-insert" class="primary" disabled>上传并插入</button><progress max="100" value="0"></progress><p class="upload-status" role="status"></p></div><h3>课程素材库</h3><input class="media-search" aria-label="搜索素材" placeholder="按名称筛选素材"><div class="media-grid">正在加载…</div>`);
 let assets=[],selectedFile;
 const list=()=>{const q=el.querySelector('.media-search').value;el.querySelector('.media-grid').innerHTML=assets.filter(a=>(!kind||a.mime.startsWith(kind+'/'))&&a.name.includes(q)).map(a=>`<div class="media-card">${mediaPreview(a)}<strong>${e(a.name)}</strong><span>${a.mime.startsWith('image/')?'图片':'视频'}</span><button data-pick="${a.id}">选择并插入</button></div>`).join('')||'<p class="muted">暂无匹配素材，可以在上方直接上传。</p>';};
 el.querySelector('.media-search').oninput=list;
 el.querySelector('#direct-upload').onchange=event=>{selectedFile=event.target.files[0];el.querySelector('#upload-name').value=selectedFile?.name||'';el.querySelector('#upload-insert').disabled=!selectedFile;};
 const choose=async a=>{await onChoose(a);el.close();};
 el.querySelector('.media-grid').onclick=async event=>{const button=event.target.closest('[data-pick]');if(button)await choose(assets.find(a=>a.id===button.dataset.pick));};
 el.querySelector('#upload-insert').onclick=async()=>{const button=el.querySelector('#upload-insert'),status=el.querySelector('.upload-status');button.disabled=true;status.textContent='上传中…';try{const a=await uploadMedia(course,selectedFile,el.querySelector('#upload-name').value,p=>el.querySelector('progress').value=p);await choose(a);}catch(err){status.textContent=err.message;button.disabled=false;}};
 try{assets=await api(`/courses/${course}/assets`);if(el.isConnected)list();}catch(err){el.querySelector('.media-grid').textContent=err.message;}
}

let resizeObserver;
export function fitGraph(zoom){
 resizeObserver?.disconnect();const scroll=document.querySelector('.graph-scroll'),svg=scroll?.querySelector('svg');if(!svg)return;
 const fit=()=>{
  const viewportWidth=scroll.clientWidth,viewportHeight=scroll.clientHeight,width=1280,height=760,focused=scroll.classList.contains('is-focused'),halfWidth=86,halfHeight=40,rx=focused?400:480,ry=focused?255:270;
  svg.setAttribute('viewBox',`0 0 ${width} ${height}`);
  svg.setAttribute('width',Math.floor(viewportWidth*zoom));svg.setAttribute('height',Math.floor(viewportHeight*zoom));
  const positions=new Map();
  svg.querySelectorAll('g[data-focus]').forEach(el=>{
   if(!el.dataset.baseX){const xy=el.getAttribute('transform').match(/[-\d.]+/g).map(Number);el.dataset.baseX=xy[0];el.dataset.baseY=xy[1];}
   const x=width/2+(Number(el.dataset.baseX)-500)/330*rx,y=height/2+(Number(el.dataset.baseY)-350)/240*ry;
   el.setAttribute('transform',`translate(${x},${y})`);positions.set(el.dataset.focus,[x,y]);
   const rect=el.querySelector('rect');rect.setAttribute('x',-halfWidth);rect.setAttribute('y',-halfHeight);rect.setAttribute('width',halfWidth*2);rect.setAttribute('height',halfHeight*2);
   const text=el.querySelector('.graph-node-title');if(text){const full=text.dataset.fullTitle,max=10;text.textContent=full.length>max?full.slice(0,max-1)+'…':full;}
   const label=el.querySelector('.graph-node-number');if(label){label.removeAttribute('textLength');if(label.getComputedTextLength()>halfWidth*2-12){label.setAttribute('textLength',halfWidth*2-12);label.setAttribute('lengthAdjust','spacingAndGlyphs');}}
  });
  const center=svg.querySelector('.chapter-center');if(center){
   center.setAttribute('transform',`translate(${width/2},${height/2})`);
   const text=center.querySelector('.chapter-center-name'),number=center.querySelector('.chapter-center-number'),title=text.dataset.fullTitle,chunks=title.match(/.{1,18}/gu)||[''];
   let available=scroll.classList.contains('chapter-graph')?360:500;
   svg.querySelectorAll('g[data-focus][aria-hidden=false]').forEach(el=>{const [x,y]=positions.get(el.dataset.focus);if(Math.abs(y-height/2)<100&&Math.abs(x-width/2)>halfWidth)available=Math.min(available,2*(Math.abs(x-width/2)-halfWidth-18));});
   text.style.fontSize='38px';text.style.letterSpacing='8px';text.replaceChildren();
   const spans=chunks.map(chunk=>{const span=document.createElementNS('http://www.w3.org/2000/svg','tspan');span.setAttribute('x','0');span.textContent=chunk;text.append(span);return span;});
   const widest=Math.max(...spans.map(span=>span.getComputedTextLength())),scale=Math.min(1,Math.max(160,available)/Math.max(1,widest)),fontSize=38*scale,lineHeight=Math.max(32,fontSize*1.7),baseline=number.textContent.trim()?18:0;
   text.style.fontSize=fontSize+'px';text.style.letterSpacing=8*scale+'px';
   spans.forEach((span,i)=>span.setAttribute('y',String((i-(spans.length-1)/2)*lineHeight+baseline)));
   number.style.fontSize=Math.max(24,fontSize*.8)+'px';
   number.setAttribute('y',String(-(spans.length-1)/2*lineHeight+baseline-Math.max(48,fontSize*1.7)));
   // SVG text-anchor includes trailing letter spacing. Center the measured
   // glyph bounds of each line instead, including the chapter ordinal.
   for(const line of [number,...spans]){line.setAttribute('x','0');const box=line.getBBox();line.setAttribute('x',String(-box.x-box.width/2));}
  }
  const halo=svg.querySelector('.demo-focus-halo');if(halo){halo.setAttribute('cx',width/2);halo.setAttribute('cy',height/2);}
  for(const [name,radius]of [['inner-orbit',185/330],['outer-orbit',1]]){const orbit=svg.querySelector('.'+name);if(orbit){orbit.setAttribute('cx',width/2);orbit.setAttribute('cy',height/2);orbit.setAttribute('rx',rx*radius);orbit.setAttribute('ry',ry*radius);}}
  const cards=new Map([...svg.querySelectorAll('g[data-focus][aria-hidden=false]')].map(el=>{const [x,y]=positions.get(el.dataset.focus);return [el.dataset.focus,{left:x-halfWidth,right:x+halfWidth,top:y-halfHeight,bottom:y+halfHeight}];}));
  const overview=!scroll.classList.contains('is-focused');
  svg.querySelectorAll('.graph-edge').forEach(el=>{const a=cards.get(el.dataset.source),b=cards.get(el.dataset.target);if(!a||!b)return;const geometry=demoEdgeGeometry(a,b,[width/2,height/2],overview);el.setAttribute('d',geometry?.d||'');el.dataset.edgeMode=overview?'curved':'straight';});
  // The expanded canvas must grow equally on both sides of the viewport.
  scroll.scrollLeft=Math.max(0,(scroll.scrollWidth-scroll.clientWidth)/2);
  scroll.scrollTop=Math.max(0,(scroll.scrollHeight-scroll.clientHeight)/2);
 };
 fit();resizeObserver=new ResizeObserver(fit);resizeObserver.observe(scroll);
}
export function captureGraph(){return new Map([...document.querySelectorAll('[data-focus]')].filter(el=>el.tagName.toLowerCase()==='g').map(el=>[el.dataset.focus,{transform:getComputedStyle(el).transform,opacity:getComputedStyle(el).opacity}]));}
export function animateGraph(previous){
 // Fade the completed SVG as one paint layer. Animating individual filtered
 // cards retains separate compositor surfaces and can leave stale silhouettes.
 const svg=document.querySelector('.demo-graph-canvas svg');if(!svg)return;
 svg.getAnimations({subtree:true}).forEach(animation=>animation.cancel());
 if(matchMedia('(prefers-reduced-motion: reduce)').matches)return;
 const changed=[...svg.querySelectorAll('g[data-focus]:not(.hidden-node)')].some(el=>previous.get(el.dataset.focus)?.transform!==getComputedStyle(el).transform);
 if(changed)svg.animate([{opacity:0},{opacity:1}],{duration:240,easing:'ease-out'});
}
