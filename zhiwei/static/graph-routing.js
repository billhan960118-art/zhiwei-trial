// Adapted from semiconductor-demo/dist/graph-layout.js edgeGeometry.
// Overview bends toward the graph center; focus uses a collinear quadratic.
export function demoEdgeGeometry(source,target,center,curved=false){
 const a=[(source.left+source.right)/2,(source.top+source.bottom)/2],b=[(target.left+target.right)/2,(target.top+target.bottom)/2];
 const dx=b[0]-a[0],dy=b[1]-a[1],length=Math.hypot(dx,dy);
 if(length<1e-6)return null;
 const sourceInset=Math.min((source.right-source.left)/2/(Math.abs(dx)||1e-9),(source.bottom-source.top)/2/(Math.abs(dy)||1e-9));
 const targetInset=Math.min((target.right-target.left)/2/(Math.abs(dx)||1e-9),(target.bottom-target.top)/2/(Math.abs(dy)||1e-9));
 const start=[a[0]+dx*sourceInset+dx/length*6,a[1]+dy*sourceInset+dy/length*6],end=[b[0]-dx*targetInset-dx/length*13,b[1]-dy*targetInset-dy/length*13];
 const midpoint=[(start[0]+end[0])/2,(start[1]+end[1])/2];
 const control=curved?[midpoint[0]+(center[0]-midpoint[0])*.28,midpoint[1]+(center[1]-midpoint[1])*.28]:midpoint;
 return {start,end,control,midpoint,d:`M ${start.join(' ')} Q ${control.join(' ')} ${end.join(' ')}`};
}
