// Node 24+: no npm dependencies. Run against `python -m fn_engine serve --headless`.
// Required: FLUIDNET_PROJECT_ID. Optional: FLUIDNET_URL, FLUIDNET_TOKEN,
// FLUIDNET_REVISION, FLUIDNET_SCENARIO, FLUIDNET_VARIABLES (comma-separated),
// FLUIDNET_WRITE_VALUES (JSON object, canonical runtime keys and units).
// No token is created or printed. Only explicitly supplied variable writes are sent.
import {randomUUID} from 'node:crypto';

const base = (process.env.FLUIDNET_URL || 'http://127.0.0.1:8798').replace(/\/$/, '');
const token = process.env.FLUIDNET_TOKEN || '';
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function request(path, body) {
  const response = await fetch(base + '/api/v1' + path, {
    method: body === undefined ? 'GET' : 'POST', signal: AbortSignal.timeout(15000),
    headers: {'Content-Type': 'application/json', ...(token ? {Authorization: 'Bearer ' + token} : {})},
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const value = await response.json();
  if (!response.ok) throw Error(`HTTP ${response.status}: ${JSON.stringify(value)}`);
  return value;
}
async function awaitRecord(id, statuses) {
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    const record = await request('/runs/' + id);
    if (record.status === 'failed') throw Error(JSON.stringify(record.frame));
    if (statuses.includes(record.status)) return record;
    await sleep(100);
  }
  throw Error('Run did not reach ' + statuses.join('/'));
}
async function awaitReceipt(id, receipt) {
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    if (receipt.command_status === 'applied') return receipt;
    if (receipt.command_status === 'rejected') throw Error(JSON.stringify(receipt));
    await sleep(100);
    const events = (await request(`/runs/${id}/events`)).events;
    receipt = events.findLast(event => event.command_id === receipt.command_id) || receipt;
  }
  throw Error('Command was accepted but did not receive an applied/rejected receipt');
}
async function command(id, action) {
  return awaitReceipt(id, await request(`/runs/${id}/command`, {action, command_id: randomUUID()}));
}
async function subscribe(id) {
  const url = new URL(base + `/api/v1/runs/${id}/stream`);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  if (process.env.FLUIDNET_VARIABLES) url.searchParams.set('keys', process.env.FLUIDNET_VARIABLES);
  const socket = new WebSocket(url, token ? ['fluidnet.bearer.' + token] : []);
  const queue = [];
  let waiting, failure;
  const deliver = () => {
    if (!waiting) return;
    if (failure) { const current = waiting; waiting = null; current.reject(failure); }
    else if (queue.length) { const current = waiting; waiting = null; current.resolve(queue.shift()); }
  };
  socket.addEventListener('message', event => {
    try { queue.push(JSON.parse(event.data)); } catch { failure = Error('Invalid stream JSON'); }
    deliver();
  });
  socket.addEventListener('error', () => { failure = Error('WebSocket connection failed'); deliver(); });
  socket.addEventListener('close', event => { failure = Error('WebSocket closed: ' + event.code); deliver(); });
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => { socket.close(); reject(Error('WebSocket open timeout')); }, 15000);
    socket.addEventListener('open', () => {clearTimeout(timer); resolve();}, {once:true});
    socket.addEventListener('error', () => {clearTimeout(timer); reject(Error('WebSocket connection failed'));}, {once:true});
  });
  return {
    close: () => socket.close(),
    async nextFrame(after = -1) {
      const deadline = Date.now() + 30000;
      while (Date.now() < deadline) {
        const value = await new Promise((resolve, reject) => {
          const timer = setTimeout(() => { waiting = null; reject(Error('No new subscribed frame')); }, Math.max(1, deadline-Date.now()));
          waiting = {resolve: value => {clearTimeout(timer); resolve(value);}, reject: error => {clearTimeout(timer); reject(error);}};
          deliver();
        });
        if (value.type === 'frame' && value.sequence > after) {
          console.log(JSON.stringify({sequence:value.sequence, time_s:value.time_s, values:Object.fromEntries(Object.entries(value.values).slice(0,8))}));
          return value;
        }
        if (['error', 'end'].includes(value.type)) throw Error(JSON.stringify(value));
      }
      throw Error('No new subscribed frame');
    },
  };
}
async function main() {
  const project = process.env.FLUIDNET_PROJECT_ID;
  if (!project) throw Error('Set FLUIDNET_PROJECT_ID to an existing saved project ID');
  const body = {mode:'dynamic', duration_s:null, dt_s:.1, start_paused:true, execution_mode:'realtime'};
  if (process.env.FLUIDNET_REVISION) body.revision = Number(process.env.FLUIDNET_REVISION);
  if (process.env.FLUIDNET_SCENARIO) body.scenario_id = process.env.FLUIDNET_SCENARIO;
  const writes = JSON.parse(process.env.FLUIDNET_WRITE_VALUES || '{}');
  if (!writes || typeof writes !== 'object' || Array.isArray(writes)) throw Error('FLUIDNET_WRITE_VALUES must be a JSON object');
  let id, stream, stopped = false;
  try {
    id = (await request('/projects/' + encodeURIComponent(project) + '/runs', body)).run_id;
    const record = await awaitRecord(id, ['paused']);
    console.log(JSON.stringify({run_id:id, project_revision:record.request.project_revision}));
    stream = await subscribe(id);
    const first = await stream.nextFrame();
    if (Object.keys(writes).length) await awaitReceipt(id, await request(`/runs/${id}/variables`, {values:writes, command_id:randomUUID(), wait_s:2}));
    await command(id, 'resume');
    const second = await stream.nextFrame(first.sequence);
    await command(id, 'pause');
    await awaitRecord(id, ['paused']);
    await command(id, 'resume');
    await stream.nextFrame(second.sequence);
    await command(id, 'stop');
    const final = await awaitRecord(id, ['cancelled']);
    stopped = true;
    console.log(JSON.stringify({status:final.status, project_revision:final.request.project_revision, final_time_s:final.frame.time_s}));
  } finally {
    stream?.close();
    if (id && !stopped) await request(`/runs/${id}/command`, {action:'stop',command_id:randomUUID()}).catch(() => {});
  }
}
main().catch(error => {console.error(error.message); process.exitCode=1;});
