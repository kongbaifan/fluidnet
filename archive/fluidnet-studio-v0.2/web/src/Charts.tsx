import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { LineChart, BarChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, ToolboxComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { Catalog, History, Project, Units } from './types';
import { displayValue, variableUnit } from './format';

echarts.use([LineChart,BarChart,GridComponent,TooltipComponent,LegendComponent,DataZoomComponent,ToolboxComponent,CanvasRenderer]);
const colors=['#07858a','#e4973a','#6982d2','#c77497','#49a186','#8c72b6','#b29155','#428cbb'];
export function TrendChart({history,project,catalog,units}:{history:History;project:Project;catalog:Catalog;units:Units}) {
  const ref=useRef<HTMLDivElement>(null);
  const chart=useRef<echarts.ECharts|null>(null);
  useEffect(()=>{if(!ref.current)return;chart.current=echarts.init(ref.current);const ro=new ResizeObserver(()=>chart.current?.resize());ro.observe(ref.current);return()=>{ro.disconnect();chart.current?.dispose();};},[]);
  useEffect(()=>{
    const unitGroups:string[]=[];
    const series=history.variables.map((path,i)=>{
      const [id,...parts]=path.split('.');const key=parts.join('.');
      const meta=catalog.variables[parts.at(-1)||'']||{label:key,unit:''};
      const unit=variableUnit(key,meta.unit,units);
      let axis=unitGroups.indexOf(unit);if(axis<0){axis=unitGroups.length;unitGroups.push(unit);}
      const element=project.elements.find(e=>e.id===id);
      return {name:`${element?.name||id} · ${meta.label}`,type:'line' as const,yAxisIndex:axis,
        showSymbol:history.rows.length<=1,symbolSize:7,sampling:'lttb' as const,connectNulls:false,
        lineStyle:{width:2},data:history.rows.map(row=>[row[0],row[i+1]==null?null:displayValue(row[i+1]!,key,meta.unit,units,project.atmosphere_pa)])};
    });
    chart.current?.setOption({animation:false,color:colors,textStyle:{fontFamily:'Segoe UI, Microsoft YaHei, sans-serif'},
      grid:{left:55,right:unitGroups.length>1?70:28,top:42,bottom:42,containLabel:true},
      tooltip:{trigger:'axis',confine:true},legend:{type:'scroll',top:2,left:20,right:70,textStyle:{fontSize:11,color:'#657983'}},
      toolbox:{right:12,top:0,feature:{saveAsImage:{title:'保存曲线 PNG',pixelRatio:3,name:project.name+'-趋势'}}},
      xAxis:{type:'value',name:'s',nameGap:10,min:0,axisLabel:{color:'#88959d',fontSize:10},splitLine:{show:false},axisLine:{lineStyle:{color:'#dce5e9'}}},
      yAxis:(unitGroups.length?unitGroups:['']).map((unit,i)=>({type:'value',name:unit,position:i===0?'left':'right',offset:Math.max(0,i-1)*50,scale:true,
        axisLabel:{color:'#88959d',fontSize:10,formatter:(n:number)=>Math.abs(n)>99999?n.toExponential(1):+n.toPrecision(4)},nameTextStyle:{color:'#70818c',fontSize:10},splitLine:{show:i===0,lineStyle:{color:'#edf1f3',type:'dashed'}}})),
      dataZoom:[{type:'inside',xAxisIndex:0},{type:'slider',height:12,bottom:2,xAxisIndex:0,borderColor:'transparent',backgroundColor:'#f1f5f6',fillerColor:'rgba(8,126,131,.12)',showDetail:false}],series},true);
  },[history,project.name,project.elements,catalog,units,project.atmosphere_pa]);
  return <div ref={ref} className="trend-chart" data-testid="trend-chart"/>;
}
