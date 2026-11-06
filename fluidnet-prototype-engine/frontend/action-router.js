/* Feature-owned action dispatch. Exact actions precede prefixes; unknown actions stay with the shell. */
window.FluidNetActionRouter = (() => {
  function create(onError) {
    const exact=new Map(),prefixes=new Map();
    const register=(table,key,handler)=>{
      if(!key||typeof handler!=='function'||table.has(key))throw Error('动作注册重复或无效：'+key);
      table.set(key,handler);return ()=>{if(table.get(key)===handler)table.delete(key);};
    };
    function invoke(handler,name,element) {
      try{const result=handler(name,element);if(result?.then)result.catch(onError);return result!==false;}
      catch(error){onError(error);return true;}
    }
    function dispatch(name,element) {
      if(exact.has(name)&&invoke(exact.get(name),name,element))return true;
      for(const [prefix,handler] of [...prefixes].sort((a,b)=>b[0].length-a[0].length))
        if(name.startsWith(prefix)&&invoke(handler,name,element))return true;
      return false;
    }
    return {action:(name,fn)=>register(exact,name,fn),prefix:(name,fn)=>register(prefixes,name,fn),dispatch};
  }
  return {create};
})();
