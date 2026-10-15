import { expect } from '@playwright/test';
import { mkdtempSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createServer } from 'node:net';

export async function testServer(){
  if(process.env.FLUIDNET_TEST_URL)return {base:process.env.FLUIDNET_TEST_URL,close:async()=>{}};
  const dir=mkdtempSync(join(tmpdir(),'fluidnet-browser-'));
  const socket=createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');
  const port=socket.address().port;await new Promise(done=>socket.close(done));
  const base=`http://127.0.0.1:${port}`;
  const server=spawn('python',['-m','fn_engine','serve','--port',String(port),'--data-dir',join(dir,'data')],{
    cwd:resolve('.'),windowsHide:true,env:{...process.env,FLUIDNET_MODULE_STORE:join(dir,'modules')},stdio:'ignore'});
  const close=async()=>{if(server.exitCode===null){const ended=once(server,'exit');server.kill();await ended;}};
  try{
    await expect.poll(async()=>{try{return (await fetch(base+'/api/v1/health')).ok;}catch{return false;}},{timeout:20000}).toBe(true);
  }catch(error){await close();throw error;}
  return {base,close};
}
