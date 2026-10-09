export class ApiError extends Error {
  diagnostic?: { code?:string; element_id?:string; message:string };
  constructor(message:string, diagnostic?:ApiError['diagnostic']) { super(message); this.diagnostic=diagnostic; }
}
export async function api<T>(path:string, body?:unknown, method?:string):Promise<T> {
  const response = await fetch('/api/v1'+path, {method:method || (body === undefined ? 'GET':'POST'),
    headers:body === undefined ? {} : {'Content-Type':'application/json'},body:body === undefined ? undefined : JSON.stringify(body)});
  if (!response.ok) {
    const json = await response.json().catch(()=>({detail:response.statusText}));
    const d = json.detail;
    const message = typeof d === 'string' ? d : Array.isArray(d) ? d.map((x:{msg:string})=>x.msg).join('；') : d?.message || '请求失败';
    throw new ApiError(message, typeof d === 'object' && !Array.isArray(d) ? d:undefined);
  }
  return response.json();
}
export function download(name:string, value:string, type='application/json') {
  const url=URL.createObjectURL(new Blob([value],{type}));
  const a=document.createElement('a');a.href=url;a.download=name;a.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}
