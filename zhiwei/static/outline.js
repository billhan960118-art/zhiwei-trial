export function descendants(outline,id){const found=new Set([id]);let size;do{size=found.size;outline.forEach(x=>{if(found.has(x.parent))found.add(x.id);});}while(size!==found.size);return found;}
// Arrays remain the authoritative sibling order; IDs and content never change.
export function moveOutline(draft,kind,id,targetKind,targetId,placement='before'){
 const list=kind==='chapter'?draft.outline:draft.nodes,item=list.find(x=>x.id===id);
 if(!item)throw Error('目录项不存在');
 if(kind===targetKind&&id===targetId)return false;
 let parent=null,target;
 if(targetKind!=='root'){
  target=(targetKind==='chapter'?draft.outline:draft.nodes).find(x=>x.id===targetId);
  if(!target)throw Error('目标目录不存在');
  parent=placement==='inside'&&targetKind==='chapter'?target.id:(targetKind==='chapter'?target.parent:target.chapter)||null;
 }
 if(kind==='chapter'&&parent&&descendants(draft.outline,id).has(parent))throw Error('不能把章节移入自身或子章节');
 const field=kind==='chapter'?'parent':'chapter';item[field]=parent;
 list.splice(list.indexOf(item),1);
 const index=kind===targetKind&&placement!=='inside'?list.findIndex(x=>x.id===targetId):-1;
 if(index>=0)list.splice(index+(placement==='after'?1:0),0,item);else list.push(item);
 return true;
}
