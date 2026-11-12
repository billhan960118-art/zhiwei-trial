import {moveOutline} from './outline.js';

export function captureSidebar(){
 const aside=document.querySelector('.shell>aside');if(!aside)return null;
 const box=aside.getBoundingClientRect();
 const row=[...aside.querySelectorAll('.tree-row')].find(el=>el.getBoundingClientRect().bottom>box.top+8);
 return {course:aside.dataset.courseId,scroll:aside.scrollTop,id:row?.dataset.treeId,offset:row?row.getBoundingClientRect().top-box.top:0};
}
export function restoreSidebar(previous,reveal){
 const aside=document.querySelector('.shell>aside');if(!aside)return;
 if(previous?.course!==aside.dataset.courseId)return;
 aside.scrollTop=previous.scroll;
 const anchor=reveal||previous,row=[...aside.querySelectorAll('.tree-row')].find(el=>el.dataset.treeId===anchor.id);
 if(row){const box=aside.getBoundingClientRect(),bounds=row.getBoundingClientRect();if(anchor.nearest&&bounds.top>=box.top+12&&bounds.bottom<=box.bottom-12)return;aside.scrollTop+=bounds.top-box.top-(anchor.nearest?aside.clientHeight*.45:anchor.offset);}
}

// A pointer drag owns one accepted target: the visible marker and commit use
// that same descriptor. No DOM hit test is performed again on mouse release.
export function installDirectoryDrag({getDraft,onMove,readOnly}){
 let drag=null,frame=0,suppressClick=false;
 const clearMarker=()=>document.querySelectorAll('[data-drop-position]').forEach(el=>{delete el.dataset.dropPosition;delete el.dataset.dropLabel;});
 const cleanup=()=>{
  cancelAnimationFrame(frame);frame=0;clearMarker();document.body.classList.remove('directory-dragging');
  document.querySelectorAll('.tree-row.dragging').forEach(el=>el.classList.remove('dragging'));
  document.querySelector('.directory-ghost')?.remove();drag=null;
 };
 function updateTarget(){
  if(!drag?.active)return;const aside=document.querySelector('.shell>aside'),box=aside.getBoundingClientRect();
  if(drag.x<box.left||drag.x>box.right||drag.y<box.top||drag.y>box.bottom){drag.target=null;clearMarker();return;}
  let row=document.elementFromPoint(drag.x,drag.y)?.closest('[data-tree-id]');
  if(!row||!aside.contains(row)){
   const rows=[...aside.querySelectorAll('.tree-row,.tree-root-drop')].filter(el=>{const b=el.getBoundingClientRect();return b.bottom>box.top&&b.top<box.bottom;});
   row=rows.reduce((best,el)=>{const b=el.getBoundingClientRect(),distance=Math.max(b.top-drag.y,drag.y-b.bottom,0);return !best||distance<best.distance?{el,distance}:best;},null)?.el;
  }
  drag.target=null;clearMarker();if(!row)return;
  const kind=row.dataset.treeKind,id=row.dataset.treeId,b=row.getBoundingClientRect();
  let placement=kind==='root'?'inside':drag.y<(b.top+b.bottom)/2?'before':'after';
  const fraction=(drag.y-b.top)/b.height;
  if(kind==='chapter'&&(drag.source.kind==='node'||fraction>=.28&&fraction<=.72))placement='inside';
  if(placement!=='inside'&&kind!==drag.source.kind)return;
  const target={kind,id,placement,offset:(placement==='before'?b.top:b.bottom)-box.top};
  try{if(!moveOutline(structuredClone(getDraft()),drag.source.kind,drag.source.id,kind,id,placement))return;}catch{return;}
  drag.target=target;row.dataset.dropPosition=placement;row.dataset.dropLabel=placement==='inside'?(kind==='root'?'移到课程顶层':'移入此章节'):placement==='before'?'插入到此处之前':'插入到此处之后';
 }
 function autoScroll(){
  if(!drag?.active)return;const aside=document.querySelector('.shell>aside'),box=aside.getBoundingClientRect();
  if(drag.x>=box.left&&drag.x<=box.right&&drag.y>=box.top&&drag.y<=box.bottom){
   const margin=48,delta=drag.y<box.top+margin?-Math.ceil((box.top+margin-drag.y)/4):drag.y>box.bottom-margin?Math.ceil((drag.y-box.bottom+margin)/4):0;
   if(delta){aside.scrollTop+=delta;updateTarget();}
  }
  frame=requestAnimationFrame(autoScroll);
 }
 document.addEventListener('pointerdown',event=>{
  if(readOnly()||event.button!==0||event.target.closest('.tree-tools'))return;
  const row=event.target.closest('.tree-row');if(!row)return;
  drag={source:{kind:row.dataset.treeKind,id:row.dataset.treeId},pointerId:event.pointerId,startX:event.clientX,startY:event.clientY,x:event.clientX,y:event.clientY,row,active:false,target:null};
 });
 document.addEventListener('pointermove',event=>{
  if(!drag||event.pointerId!==drag.pointerId)return;drag.x=event.clientX;drag.y=event.clientY;
  if(!drag.active){if(Math.hypot(drag.x-drag.startX,drag.y-drag.startY)<6)return;drag.active=true;suppressClick=true;drag.row.setPointerCapture(event.pointerId);drag.row.classList.add('dragging');document.body.classList.add('directory-dragging');const ghost=document.createElement('div');ghost.className='directory-ghost';ghost.textContent=drag.row.querySelector('.tree-label').textContent;document.body.append(ghost);frame=requestAnimationFrame(autoScroll);}
  event.preventDefault();const ghost=document.querySelector('.directory-ghost');ghost.style.left=drag.x+14+'px';ghost.style.top=drag.y+12+'px';updateTarget();
 },{passive:false});
 document.addEventListener('pointerup',event=>{
  if(!drag||event.pointerId!==drag.pointerId)return;const {active,source,target}=drag;cleanup();
  if(active){event.preventDefault();if(target)onMove(source,target);setTimeout(()=>suppressClick=false,0);}
 });
 document.addEventListener('pointercancel',()=>{cleanup();suppressClick=false;});
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&drag){cleanup();setTimeout(()=>suppressClick=false,0);}});
 document.addEventListener('click',event=>{if(suppressClick){event.preventDefault();event.stopImmediatePropagation();suppressClick=false;}},true);
 document.addEventListener('dragstart',event=>{if(event.target.closest('.tree-row'))event.preventDefault();});
}
