/* Reconcile generated SVG children without replacing active canvas and chart elements. */
window.FluidNetSvgDom = (() => {
  const key=node=>{
    if(node.nodeType!==1)return null;
    for(const attribute of ['id','data-canvas-edge','data-node','data-trace-edge','data-edge','data-series-key','data-hover-mark','data-chart-hit','data-port-id'])
      if(node.hasAttribute(attribute))return node.localName+':'+attribute+':'+node.getAttribute(attribute);
    return null;
  };
  const compatible=(a,b)=>a.nodeType===b.nodeType&&(a.nodeType!==1||a.localName===b.localName&&a.namespaceURI===b.namespaceURI);
  function sync(target,source){
    if(target.nodeType!==1){if(target.nodeValue!==source.nodeValue)target.nodeValue=source.nodeValue;return;}
    for(const attribute of [...target.attributes])if(!source.hasAttributeNS(attribute.namespaceURI,attribute.localName))target.removeAttributeNode(attribute);
    for(const attribute of source.attributes)if(target.getAttributeNS(attribute.namespaceURI,attribute.localName)!==attribute.value)
      target.setAttributeNS(attribute.namespaceURI,attribute.name,attribute.value);
    children(target,source);
  }
  function children(target,source){
    const previous=[...target.childNodes],remaining=new Set(previous),keyed=new Map(previous.map(node=>[key(node),node]).filter(([id])=>id!==null));
    let cursor=target.firstChild;
    for(const wanted of [...source.childNodes]){
      const id=key(wanted);
      let kept=id!==null?keyed.get(id):previous.find(node=>remaining.has(node)&&key(node)===null&&compatible(node,wanted));
      if(kept&&(!remaining.has(kept)||!compatible(kept,wanted)))kept=null;
      if(kept){remaining.delete(kept);sync(kept,wanted);}else kept=wanted.cloneNode(true);
      if(kept!==cursor)target.insertBefore(kept,cursor);
      cursor=kept.nextSibling;
    }
    for(const node of remaining)node.remove();
  }
  function patch(target,markup){
    if(!target)return;
    const source=target.cloneNode(false);source.innerHTML=markup;
    children(target,source);
  }
  function update(target,markup){
    if(!target)return;
    const holder=target.ownerDocument.createElement('template');holder.innerHTML=markup;
    const source=holder.content.firstElementChild;
    if(!source||!compatible(target,source))throw Error('SVG update requires the same root element');
    sync(target,source);
  }
  return {patch,update};
})();
