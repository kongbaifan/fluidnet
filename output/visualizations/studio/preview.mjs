import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';

const source = new URL('../fluidnet-studio-prototype.html', import.meta.url);
let port = Number(process.argv[2] || 8789);
const server = createServer(async (request, response) => {
  if (request.url === '/favicon.ico') { response.writeHead(204); response.end(); return; }
  if (!['/', '/index.html'].includes(request.url?.split('?')[0])) { response.writeHead(404); response.end('Not found'); return; }
  try {
    const html = await readFile(source);
    response.writeHead(200, { 'Content-Type':'text/html; charset=utf-8', 'Cache-Control':'no-store' });
    response.end(html);
  } catch { response.writeHead(500); response.end('Build the prototype before previewing.'); }
});
server.on('error', error => {
  if (error.code === 'EADDRINUSE' && port < 8799) server.listen(++port, '127.0.0.1');
  else { console.error(error.message); process.exitCode = 1; }
});
server.on('listening', () => console.log(`FluidNet prototype: http://127.0.0.1:${port}/`));
server.listen(port, '127.0.0.1');
