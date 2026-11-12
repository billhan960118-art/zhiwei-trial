import {descendants} from './outline.js';
export function directoryNumbers(draft){
 const chapters=new Map(),nodes=new Map();
 function visit(parent=null,prefix=''){
  const children=draft.outline.filter(x=>(x.parent||null)===parent);
  children.forEach((x,i)=>{const number=prefix+(i+1);chapters.set(x.id,number);visit(x.id,number+'.');});
  draft.nodes.filter(n=>!n.archived&&(n.chapter||null)===parent).forEach((n,i)=>nodes.set(n.id,prefix+(children.length+i+1)));
 }
 visit();return {chapters,nodes};
}
export function chapterGraph(draft,chapterId){
 const chapterIds=descendants(draft.outline,chapterId),all=draft.nodes.filter(n=>!n.archived),internal=new Set(all.filter(n=>chapterIds.has(n.chapter)).map(n=>n.id));
 const external=new Set(draft.relations.filter(r=>internal.has(r.source)||internal.has(r.target)).flatMap(r=>[r.source,r.target]).filter(id=>!internal.has(id)&&all.some(n=>n.id===id)));
 const visible=new Set([...internal,...external]),positions=new Map();
 for(const [ids,rx,ry]of [[internal,185,134],[external,330,240]])[...ids].forEach((id,i)=>{const a=-Math.PI/2+2*Math.PI*i/ids.size;positions.set(id,[500+rx*Math.cos(a),350+ry*Math.sin(a)]);});
 // Keep invisible nodes available for the existing fade animation and keyboard rules.
 all.forEach(n=>{if(!positions.has(n.id))positions.set(n.id,[500,350]);});
 return {all,internal,external,visible,positions};
}
export function matchesQuery(node,query){const q=query.trim().toLocaleLowerCase();return Boolean(q)&&(node.title+' '+(node.tags||[]).join(' ')).toLocaleLowerCase().includes(q);}

export function knowledgeGraph(draft,chapterId,focus){
 const all=draft.nodes.filter(n=>!n.archived),active=new Set(all.map(n=>n.id));
 let model;
 if(!focus&&chapterId)model=chapterGraph(draft,chapterId);
 else{
  const visible=new Set(focus?[focus,...draft.relations.filter(r=>r.source===focus||r.target===focus).flatMap(r=>[r.source,r.target]).filter(id=>active.has(id))]:all.map(n=>n.id)),positions=new Map();
  all.forEach((n,i)=>{const a=-Math.PI/2+2*Math.PI*i/Math.max(1,all.length);positions.set(n.id,[500+330*Math.cos(a),350+240*Math.sin(a)]);});
  if(focus){const neighbors=all.filter(n=>visible.has(n.id)&&n.id!==focus);neighbors.forEach((n,i)=>{const a=-Math.PI/2+2*Math.PI*i/Math.max(1,neighbors.length);positions.set(n.id,[500+330*Math.cos(a),350+240*Math.sin(a)]);});positions.set(focus,[500,350]);}
  model={all,visible,positions};
  if(chapterId){const chapters=descendants(draft.outline,chapterId);model.internal=new Set(all.filter(n=>visible.has(n.id)&&chapters.has(n.chapter)).map(n=>n.id));model.external=new Set([...visible].filter(id=>!model.internal.has(id)));}
 }
 model.edges=draft.relations.filter(r=>model.visible.has(r.source)&&model.visible.has(r.target)&&(!focus||r.source===focus||r.target===focus));
 return model;
}
