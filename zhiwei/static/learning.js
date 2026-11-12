import {directoryNumbers} from './graph-view.js';

export function chapterLabel(number){return number?'第 '+number+' 章':'未分章';}

export function learningModel(draft,doneIds=[]){
 const done=new Set(Array.isArray(doneIds)?doneIds:[]),nodes=draft.nodes.filter(n=>!n.archived),numbers=directoryNumbers(draft),directory=[];
 function collect(parent=null){draft.outline.filter(c=>(c.parent||null)===parent).forEach(c=>collect(c.id));directory.push(...nodes.filter(n=>(n.chapter||null)===parent));}
 collect();for(const node of nodes)if(!directory.includes(node))directory.push(node);
 const remaining=[...directory],ordered=[];
 while(remaining.length){const index=remaining.findIndex(n=>!draft.relations.some(r=>r.type==='prerequisite'&&r.target===n.id&&remaining.some(x=>x.id===r.source)));if(index<0){ordered.push(...remaining);break;}ordered.push(remaining.splice(index,1)[0]);}
 const stats=list=>({total:list.length,learned:list.filter(n=>done.has(n.id)).length,pending:list.filter(n=>!done.has(n.id)).length});
 function group(chapter){const direct=ordered.filter(n=>n.chapter===chapter.id),children=draft.outline.filter(c=>c.parent===chapter.id).map(group),all=[...direct,...children.flatMap(c=>c.all)];return {id:chapter.id,title:chapter.title,number:numbers.chapters.get(chapter.id),direct,children,all,...stats(all)};}
 const groups=draft.outline.filter(c=>!c.parent).map(group),unassigned=ordered.filter(n=>!n.chapter||!draft.outline.some(c=>c.id===n.chapter));
 if(unassigned.length)groups.push({id:'unassigned',title:'未分章知识点',number:null,direct:unassigned,children:[],all:unassigned,...stats(unassigned)});
 return {groups,numbers,done,ordered,next:ordered.find(n=>!done.has(n.id)),...stats(nodes)};
}
