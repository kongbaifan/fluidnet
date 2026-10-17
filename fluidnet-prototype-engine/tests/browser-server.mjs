import { mkdtempSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createServer } from 'node:net';

// Windows 会把一部分动态端口留给系统（含 Hyper-V 保留段），所以 listen(0) 拿到的端口
// 在 close 之后仍可能被拒绝绑定（WSAEACCES / Errno 13）。启动服务必须可重试并换端口。
async function freePort(){
  const socket=createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');
  const port=socket.address().port;await new Promise(done=>socket.close(done));return port;
}
const sleep=ms=>new Promise(done=>setTimeout(done,ms));
async function endServer(server){
  if(!server||server.exitCode!==null)return;
  const ended=once(server,'exit');server.kill();await ended;
}

export async function launchEngine({args=[],env={},attempts=5,waitMs=15000}={}){
  let lastLog='';
  for(let attempt=0;attempt<attempts;attempt++){
    const port=await freePort();
    const base=`http://127.0.0.1:${port}`;
    let log='';
    const server=spawn('python',['-m','fn_engine','serve','--host','127.0.0.1','--port',String(port),...args],{
      cwd:resolve('.'),windowsHide:true,env:{...process.env,...env},stdio:['ignore','ignore','pipe']});
    server.stderr.on('data',chunk=>{log=(log+chunk).slice(-4000);});
    const deadline=Date.now()+waitMs;
    let ready=false;
    while(Date.now()<deadline){
      // A dead process cannot become healthy; retry a new port instead of burning waitMs.
      if(server.exitCode!==null)break;
      try{ if((await fetch(base+'/api/v1/health')).ok){ready=true;break;} }catch{}
      await sleep(250);
    }
    if(ready)return {server,port,base,log:()=>log,stop:()=>endServer(server)};
    await endServer(server);
    await sleep(200);
    lastLog=log;
  }
  throw Error('启动 fn_engine 服务失败：'+(lastLog.slice(-2500)||'（没有 stderr 输出）'));
}

export async function testServer(){
  if(process.env.FLUIDNET_TEST_URL)return {base:process.env.FLUIDNET_TEST_URL,close:async()=>{}};
  const dir=mkdtempSync(join(tmpdir(),'fluidnet-browser-'));
  const launched=await launchEngine({args:['--data-dir',join(dir,'data')],env:{FLUIDNET_MODULE_STORE:join(dir,'modules')}});
  return {base:launched.base,close:launched.stop};
}
