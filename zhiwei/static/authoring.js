export const relationNames={prerequisite:'前置知识',reference:'内容参考'};
export const relationType=type=>['prerequisite','derivation','application'].includes(type)?'prerequisite':'reference';
export function referenceSummary(draft,nodeId){
 const active=new Map(draft.nodes.filter(n=>!n.archived).map(n=>[n.id,n])),groups={prerequisite:new Set(),reference:new Set()};
 for(const r of draft.relations){
  if(!active.has(r.source)||!active.has(r.target)||r.source===r.target)continue;
  const type=relationType(r.type);
  if(type==='prerequisite'&&r.target===nodeId)groups.prerequisite.add(r.source);
  if(type==='reference'&&(r.source===nodeId||r.target===nodeId))groups.reference.add(r.source===nodeId?r.target:r.source);
 }
 return Object.fromEntries(Object.entries(groups).map(([type,ids])=>[type,[...ids].map(id=>active.get(id))]));
}
const key=r=>r.type==='reference'?JSON.stringify([r.type,...[r.source,r.target].sort()]):JSON.stringify([r.type,r.source,r.target]);

// Preserve legacy content; fold old relationship categories into the two
// supported categories. References own only the edges they generated.
export function syncReferences(draft){
 const relations=new Map();
 for(const old of draft.relations||[]){
  if(old.fromReferences)continue;
  const r={...old,type:relationType(old.type)};delete r.referenceBlocks;
  const existing=relations.get(key(r));
  if(!existing)relations.set(key(r),r);
  else if(r.reason&&r.reason!==existing.reason)existing.reason=[existing.reason,r.reason].filter(Boolean).join('；');
 }
 const active=new Set(draft.nodes.filter(n=>!n.archived).map(n=>n.id));
 for(const node of draft.nodes){
  for(const block of node.sections.flatMap(s=>s.blocks)){
   if(block.type!=='reference')continue;
   const d=block.data;d.relationType=relationType(d.relationType);
   if(!active.has(node.id)||!active.has(d.target)||node.id===d.target)continue;
   // “前置知识” means the selected knowledge is a prerequisite of this node.
   const edge={source:d.relationType==='prerequisite'?d.target:node.id,target:d.relationType==='prerequisite'?node.id:d.target,type:d.relationType};
   const k=key(edge),r=relations.get(k)||{...edge,id:'reference-'+block.blockId,reason:'知识引用',fromReferences:true};
   r.referenceBlocks=[...(r.referenceBlocks||[]),block.blockId];relations.set(k,r);
  }
 }
 draft.relations=[...relations.values()];return draft;
}

export function removeRelationship(draft,id){
 const relation=draft.relations.find(r=>r.id===id),blocks=new Set(relation?.referenceBlocks||[]);
 for(const node of draft.nodes)for(const section of node.sections)section.blocks=section.blocks.filter(b=>!blocks.has(b.blockId));
 draft.relations=draft.relations.filter(r=>r.id!==id);
}

export function referenceHosts(draft,relation){
 const ids=relation.type==='prerequisite'?[relation.target]:[relation.source,relation.target];
 return draft.nodes.filter(n=>!n.archived&&ids.includes(n.id));
}

// Explicit placement is shared by relationship maintenance and the editor.
// Validate before mutating so stale dialogs cannot partially change content.
export function placeReference(draft,relation,{hostId,sectionId,beforeId,blockId,newSectionId,newBlockId,sectionTitle='关联知识'}){
 const host=referenceHosts(draft,relation).find(n=>n.id===hostId);
 if(!host)throw Error('请选择可插入引用的知识点');
 let section=host.sections.find(s=>s.sectionId===sectionId);
 if(sectionId&&!section)throw Error('所选条目已不存在，请重新选择');
 if(!section&&!newSectionId)throw Error('请选择条目');
 const existing=blockId?host.sections.flatMap(s=>s.blocks).find(b=>b.blockId===blockId&&b.type==='reference'):null;
 if(blockId&&!existing)throw Error('原引用已不存在，请重新选择');
 if(beforeId&&(!section||!section.blocks.some(b=>b.blockId===beforeId&&b.blockId!==blockId)))throw Error('插入位置已变化，请重新选择');
 if(!existing&&!newBlockId)throw Error('引用标识无效');
 if(!section){section={sectionId:newSectionId,title:sectionTitle.trim()||'关联知识',semanticKind:'custom',blocks:[]};host.sections.push(section);}
 const block=existing||{blockId:newBlockId,type:'reference',blockVersion:1,data:{target:hostId===relation.source?relation.target:relation.source,relationType:relation.type,anchor:''}};
 if(existing)for(const s of host.sections)s.blocks=s.blocks.filter(b=>b!==existing);
 const index=beforeId?section.blocks.findIndex(b=>b.blockId===beforeId):section.blocks.length;
 section.blocks.splice(index,0,block);syncReferences(draft);return block;
}
