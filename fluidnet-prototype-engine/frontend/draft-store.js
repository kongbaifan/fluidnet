/* Lossless local draft format. Acyclic JSON nodes share storage, never mutable decoded objects. */
window.FluidNetDraftStore=(()=>{
  const FORMAT='fluidnet-local-draft-v2';
  function pack(value){
    const nodes=[],known=new Map();
    function visit(v){
      let node;
      if(Array.isArray(v))node=['a',v.map(visit)];
      else if(v&&typeof v==='object')node=['o',Object.entries(v).filter(([,x])=>x!==undefined).map(([k,x])=>[k,visit(x)])];
      else node=['v',v===undefined?null:v];
      const key=JSON.stringify(node);if(known.has(key))return known.get(key);
      const id=nodes.length;nodes.push(node);known.set(key,id);return id;
    }
    const root=visit(value);return JSON.stringify({format:FORMAT,root,nodes});
  }
  function decode(value){
    if(value?.format!==FORMAT)return value;
    if(!Array.isArray(value.nodes)||value.nodes.length>2000000||!Number.isInteger(value.root))throw Error('本地草稿索引无效');
    let expanded=0;
    function read(id,depth=0){
      if(!Number.isInteger(id)||id<0||id>=value.nodes.length||depth>120||++expanded>5000000)throw Error('本地草稿引用无效或超限');
      const node=value.nodes[id];if(!Array.isArray(node)||node.length!==2)throw Error('本地草稿节点无效');
      if(node[0]==='v'){
        if(node[1]!==null&&typeof node[1]==='object'||typeof node[1]==='number'&&!Number.isFinite(node[1]))throw Error('本地草稿值无效');
        return node[1];
      }
      if(!Array.isArray(node[1]))throw Error('本地草稿容器无效');
      const ref=x=>{if(!Number.isInteger(x)||x>=id)throw Error('本地草稿循环或前向引用');return read(x,depth+1);};
      if(node[0]==='a')return node[1].map(ref);
      if(node[0]==='o'){
        const out={};for(const pair of node[1]){
          if(!Array.isArray(pair)||pair.length!==2||typeof pair[0]!=='string'||Object.hasOwn(out,pair[0]))throw Error('本地草稿对象无效');
          Object.defineProperty(out,pair[0],{value:ref(pair[1]),enumerable:true,writable:true,configurable:true});
        }return out;
      }
      throw Error('未知本地草稿格式');
    }
    return read(value.root);
  }
  function parse(text){return decode(JSON.parse(text));}
  function write(storage,key,text){
    try{storage.setItem(key,text);return {packed:false,chars:text.length};}
    catch(error){if(!/quota|存储空间/i.test(String(error.name)+' '+String(error.message))&&![22,1014].includes(error.code))throw error;
      const packed=pack(JSON.parse(text));if(packed.length>=text.length)throw error;
      storage.setItem(key,packed);return {packed:true,chars:packed.length};}
  }
  return {pack,decode,parse,write};
})();
