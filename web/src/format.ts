import type { ParameterDef, Units } from './types';

export function variableUnit(key:string, raw:string, units:Units) {
  const last=key.split('.').at(-1)||key;
  if(raw==='Pa') return units.pressure==='gauge' && last!=='pressure_drop_pa' ? 'kPa(g)':'kPa';
  if(raw==='K') return units.temperature==='celsius'?'°C':'K';
  return raw;
}
export function displayValue(value:number, key:string, raw:string, units:Units, atmosphere=101325) {
  if(raw==='Pa') return (value-(units.pressure==='gauge' && !key.endsWith('pressure_drop_pa')?atmosphere:0))/1000;
  if(raw==='K') return value-(units.temperature==='celsius'?273.15:0);
  return value;
}
export function numberText(value:number|null|undefined, digits=4) {
  if(value==null || !Number.isFinite(value)) return '—';
  if(value===0) return '0';
  if(Math.abs(value)<0.0001 || Math.abs(value)>=1e7) return value.toExponential(3);
  return Number(value.toPrecision(digits)).toLocaleString('en-US',{maximumFractionDigits:6});
}
export function parameterDisplay(def:ParameterDef, value:number, units:Units, atmosphere:number) {
  if(def.key==='diameter_m'||def.key==='roughness_m') return {value:value*1000,unit:'mm'};
  return {value:displayValue(value,def.key,def.unit||'',units,atmosphere),unit:variableUnit(def.key,def.unit||'',units)};
}
export function parameterParse(def:ParameterDef, value:number, units:Units, atmosphere:number) {
  if(def.key==='diameter_m'||def.key==='roughness_m') return value/1000;
  if(def.unit==='Pa') return value*1000+(units.pressure==='gauge'?atmosphere:0);
  if(def.unit==='K') return value+(units.temperature==='celsius'?273.15:0);
  return value;
}
export const statusLabel:Record<string,string>={idle:'就绪',queued:'队列中',running:'运行中',paused:'已暂停',completed:'已完成',converged:'已收敛',stopped:'已停止',failed:'计算失败',event:'到达事件边界',interrupted:'已中断'};
