const STORAGE_KEY = 'fluidnet-studio-prototype-20261009-v1';
const UI_KEY = STORAGE_KEY + '-ui';
const PAGE_META = {
  home:['首页','Home','项目、模块与任务概览'],
  projects:['项目','FolderOpen','项目管理与示例'],
  workbench:['建模','Network','管网建模与设备调节'],
  modules:['模块','Boxes','模块库与开发入口'],
  editor:['模块开发','Box','图形、变量、代码与通路'],
  nodes:['节点定义','Waypoints','四类端口与连接约定'],
  models:['型号','Database','设备型号与版本管理'],
  curves:['曲线','Activity','变量曲线与工况对照'],
  runs:['记录','History','运行记录、参数与导出'],
  controls:['控制','Code2','控制逻辑与观察变量'],
  settings:['设置','Settings2','介质、求解与显示'],
  help:['指南','BookOpen','页面导览与使用流程']
};
const EDITOR_TABS = [['drawing','绘制模块','SquareDashed'],['attributes','变量属性','List'],['values','变量值','Table2'],['models','设备型号','Database'],['code','代码','Code2'],['channels','通路设置','Waypoints']];
const DOMAINS = { fluid:{label:'流体',color:'orange',unit:'kg/s',icon:'Droplets'}, info:{label:'信息',color:'green',unit:'—',icon:'Activity'}, power:{label:'电力',color:'purple',unit:'A',icon:'Zap'}, mech:{label:'机械',color:'blue',unit:'N·m',icon:'RotateCw'} };
const PARAM_DEFS = {
  source:[['pressure','绝对压力','kPa',110,1000,1,201.325],['temperature','温度','°C',1,90,1,20]],
  pump:[['speed','转速比','倍',.2,1.3,.05,1],['efficiency','泵效率','%',1,100,1,75]],
  valve:[['opening','阀门开度','%',0,100,1,80],['kv','流量系数 Kv','m³/h',.1,200,.5,16]],
  pipe:[['length','管道长度','m',.1,1000,.5,30],['diameter','管道内径','mm',5,1000,1,40]],
  junction:[['elevation','标高','m',-100,1000,.1,0]],
  tank:[['level','初始液位','m',.1,10,.1,2],['area','横截面积','m²',.1,100,.1,2.5]],
  exchanger:[['ua','传热系数 UA','W/K',1,50000,100,2000],['loss','阻力系数','—',0,1000,.1,5]],
  heater:[['power','加热功率','kW',0,1000,1,20]],
  sensor:[['range','量程上限','kg/s',.1,1000,1,10]],
  pid:[['setpoint','目标值','°C',0,100,.1,45],['kp','比例增益','—',0,1000,.1,2]],
  refprop:[],
  check:[['loss','阻力系数','—',0,1000,.1,2]]
};
const MODULE_SPECS = [
  ['source','压力边界','BOUNDARY','边界与节点','Droplets','为回路提供压力与温度边界。'],
  ['junction','连接节点','JUNCTION','边界与节点','Waypoints','连接多条支路，表达节点守恒关系。'],
  ['tank','储水罐','TANK','边界与节点','Database','包含液位、容积和储能状态的设备。'],
  ['pipe','圆管','PIPE','管道与阻力','Minus','长度、内径与阻力参数共同定义管段。'],
  ['valve','调节阀','VALVE','管道与阻力','SlidersHorizontal','通过开度调节支路，支持型号参数复用。'],
  ['check','止回阀','CHECK','管道与阻力','ArrowRightLeft','单向流动元件与局部阻力参数。'],
  ['pump','离心泵','PUMP','流体机械','Triangle','泵转速与性能参数的可调设备。'],
  ['exchanger','双侧换热器','HEAT_EXCHANGER','热力设备','ArrowRightLeft','两个独立流体通路，通过换热关联。'],
  ['heater','加热器','HEATER','热力设备','Flame','向流体侧输入热量的功率设备。'],
  ['sensor','流量计','FLOW_METER','测量与控制','Gauge','将支路流量关联到观察与曲线。'],
  ['pid','PID 控制器','PID','测量与控制','Activity','输入、设定与输出组成控制关系。'],
  ['refprop','物性测试','REFPROPTEST','自定义模块','Box','工质、组成与物性接口的编辑示例。']
];
const FLUIDS = [['water','水',125],['air','空气',3],['ammonia','氨',4],['co2','二氧化碳',17],['r134a','R134a',92]];
const SERIES = { q:{name:'主管流量',short:'主管',unit:'kg/s',color:'blue'},a:{name:'A 路流量',short:'A 路',unit:'kg/s',color:'orange'},b:{name:'B 路流量',short:'B 路',unit:'kg/s',color:'green'},pressure:{name:'出口压力',short:'压力',unit:'kPa',color:'blue'},temperature:{name:'出口温度',short:'温度',unit:'°C',color:'orange'} };
const clone = v => JSON.parse(JSON.stringify(v));
const defaultsFor = id => Object.fromEntries((PARAM_DEFS[id]||[]).map(f=>[f[0],f[6]]));
function port(id,name,label,direction,domain='fluid',x=direction==='in'?20:80,y=50) { return {id,name,label,direction,domain,x,y}; }
function portsFor(id) {
  if(id==='source') return [port('out0','EX0','边界接口','out','fluid',78,50)];
  if(id==='junction') return [port('in0','IM0','公共口','in','fluid',20,50),port('out0','EX0','A 支路','out','fluid',80,30),port('out1','EX1','B 支路','out','fluid',80,70)];
  if(id==='exchanger') return [port('in0','IM0','一次侧入口','in','fluid',20,30),port('out0','EX0','一次侧出口','out','fluid',80,30),port('in1','IM1','二次侧入口','in','fluid',20,70),port('out1','EX1','二次侧出口','out','fluid',80,70)];
  if(id==='pid') return [port('in0','II0','测量输入','in','info'),port('out0','IO0','控制输出','out','info')];
  if(id==='refprop') return [port('in0','IM0','物性输入','in')];
  return [port('in0','IM0',id==='tank'?'进水口':'入口','in'),port('out0','EX0',id==='tank'?'出水口':'出口','out')];
}
function variablesFor(m) {
  const entries=[];
  for(const p of m.ports) {
    const items=p.domain==='fluid' ? [['FLOW','质量流量','kg/s',0],['PRE','绝对压力','MPa',.201325],['ENTHALPY','比焓','kJ/kg',83.9],['TEMP','温度','°C',20],['VOLUME','密度','kg/m³',998.2],['Q','干度','—',0],['X','质量组分','—',[1,0,0,0,0,0,0,0]]] : [['VALUE',p.domain==='info'?'信号值':p.domain==='power'?'电流':'转矩',DOMAINS[p.domain].unit,0]];
    for(const [suffix,label,unit,value] of items) entries.push({id:p.id+':'+suffix,name:p.name+'_'+suffix,label:p.label+' · '+label,unit,type:Array.isArray(value)?'double[8]':'double',port:p.id,origin:'port',note:suffix==='VOLUME'?'密度；参考字段 VOLUME':label,display:['FLOW','PRE'].includes(suffix),writable:p.direction==='in',value});
  }
  for(const f of PARAM_DEFS[m.kind]||[]) entries.push({id:'param:'+f[0],name:f[0].toUpperCase(),label:f[1],unit:f[2],type:'double',port:'',origin:'parameter',param:f[0],note:f[1],display:true,writable:true,value:f[6]});
  entries.push({id:'system:step',name:'S_T',label:'时间步长',unit:'ms',type:'int',port:'',origin:'system',note:'每次演示推进的时间',display:false,writable:true,value:100},{id:'system:run',name:'RUN_S',label:'运行状态',unit:'—',type:'int',port:'',origin:'system',note:'0：就绪 / 暂停；1：运行',display:false,writable:false,value:0},{id:'system:mix',name:'MIX',label:'工质质量比例',unit:'—',type:'double[8]',port:'',origin:'system',note:'与 FORM 顺序对应',display:false,writable:true,value:[1,0,0,0,0,0,0,0]},{id:'system:form',name:'FORM',label:'工质编号',unit:'—',type:'int[8]',port:'',origin:'system',note:'工质种类；最多 8 组分',display:false,writable:true,value:[125,0,0,0,0,0,0,0]});
  return entries;
}
function makeModule(spec) {
  const [id,name,code,category,icon,description]=spec;
  const m={id,kind:id,name,code,category,icon,description,version:1,ports:portsFor(id),channels:[],customVars:[],quickParam:(PARAM_DEFS[id]||[])[0]?.[0]||'',quickType:id==='pump'?'number':'slider',drawing:{shape:'rectangle',width:32,height:30,label:name},step:100,precision:4,dirty:false};
  if(!['source','junction','tank','refprop','pid'].includes(id)) m.channels=[{id:'ch0',name:'通路 0',input:'in0',output:'out0',kind:'resistance',enabled:true}];
  if(id==='exchanger')m.channels.push({id:'ch1',name:'通路 1',input:'in1',output:'out1',kind:'resistance',enabled:true});
  m.variables=variablesFor(m);m.values=Object.fromEntries(m.variables.map(v=>[v.id,clone(v.value)]));
  m.banks=[clone(m.values),clone(m.values),clone(m.values)];m.bankNames=['额定工况','部分负荷','调试备份'];
  if(id==='valve'){m.banks[1]['param:opening']=65;m.banks[2]['param:opening']=40;}
  m.source={runtime:`// ${code} · 运行函数\n// 参数与端口由模块定义提供\n\nvoid Run() {\n  // 读取已接受的端口状态\n  double opening = OPENING / 100.0;\n\n  // 提供设备关系，由全网统一求解\n  // 运行代码在本原型中仅作编辑预览\n}\n`,header:`#pragma once\n\n// ${code} · 公共声明\nstruct PortState {\n  double pressure;    // Pa\n  double temperature; // K\n  double density;     // kg/m³\n};\n`,design:[`// 库值 1 · 额定工况\nvoid Design1() {\n  OPENING = 80.0;\n  KV = 16.0;\n}\n`,`// 库值 2 · 部分负荷\nvoid Design2() {\n  OPENING = 65.0;\n  KV = 16.0;\n}\n`,`// 库值 3 · 调试备份\nvoid Design3() {\n  OPENING = 40.0;\n  KV = 16.0;\n}\n`]};
  if(id!=='valve'){m.source.runtime=`// ${code} · 运行函数\nvoid Run() {\n  // 在此编辑设备算法\n  // 当前原型不编译或执行代码\n}\n`;m.source.design=[1,2,3].map(i=>`// ${code} · 库值 ${i}\nvoid Design${i}() {\n  // 编辑设计参数\n}\n`);}
  return m;
}
function makeInstance(id,kind,name,x,y,params={}) { const p={...defaultsFor(kind),...params};return {id,moduleId:kind,name,x,y,rotation:0,params:p,draft:clone(p),modelId:kind==='valve'?'valve-16':kind==='pump'?'pump-standard':null,modelVersion:1,draftModelId:null}; }
function waterPage(){return {id:'main',name:'主系统',zoom:1,pan:[0,0],nodes:[makeInstance('B1','source','供水边界',70,225),makeInstance('P1','pump','循环泵',230,225),makeInstance('N1','junction','分流节点',380,225),makeInstance('V1','valve','A 路调节阀',515,135),makeInstance('L1','pipe','A 路管道',685,135),makeInstance('V2','valve','B 路调节阀',515,335,{opening:55}),makeInstance('L2','pipe','B 路管道',685,335,{length:40}),makeInstance('N2','junction','汇流节点',830,225),makeInstance('B2','source','回水边界',975,225,{pressure:120})],edges:[['e1','B1','out0','P1','in0'],['e2','P1','out0','N1','in0'],['e3','N1','out0','V1','in0'],['e4','V1','out0','L1','in0'],['e5','L1','out0','N2','out0'],['e6','N1','out1','V2','in0'],['e7','V2','out0','L2','in0'],['e8','L2','out0','N2','out1'],['e9','N2','in0','B2','out0']]};}
function heatPage(){return {id:'main',name:'一次与二次回路',zoom:1,pan:[0,0],nodes:[makeInstance('B1','source','一次侧供水',100,155,{temperature:65}),makeInstance('P1','pump','一次泵',290,155),makeInstance('HX1','exchanger','板式换热器',545,235),makeInstance('B2','source','一次侧回水',825,155,{pressure:120}),makeInstance('B3','source','二次侧供水',100,335,{temperature:25}),makeInstance('P2','pump','二次泵',290,335),makeInstance('B4','source','二次侧回水',825,335,{pressure:120})],edges:[['h1','B1','out0','P1','in0'],['h2','P1','out0','HX1','in0'],['h3','HX1','out0','B2','out0'],['h4','B3','out0','P2','in0'],['h5','P2','out0','HX1','in1'],['h6','HX1','out1','B4','out0']]};}
function tankPage(){return {id:'main',name:'储水与调节',zoom:1,pan:[0,0],nodes:[makeInstance('B1','source','补水边界',120,230),makeInstance('V1','valve','进水调节阀',330,230,{opening:65}),makeInstance('TK1','tank','储水罐',540,230),makeInstance('V2','valve','出水调节阀',750,230,{opening:40}),makeInstance('B2','source','回水边界',960,230,{pressure:120})],edges:[['t1','B1','out0','V1','in0'],['t2','V1','out0','TK1','in0'],['t3','TK1','out0','V2','in0'],['t4','V2','out0','B2','out0']]};}
function emptyRun(scope='project') {return {scope,status:'ready',time:0,step:.1,history:[],events:[],id:'',values:{q:0,a:0,b:0,pressure:0,temperature:20}};}
function makeProject(id,name,description,page){return {id,name,description,pages:[page],activePage:'main',modified:'示例项目',medium:'water',run:emptyRun(),solver:{duration:30,dt:.1,massAtol:1e-7,pressureAtol:.1,maxIter:80,mode:'dynamic'},control:`-- 供水温度调节 · 控制逻辑示例\n-- 原型只编辑与预览，不执行脚本\nlocal target = 45.0\nlocal measured = get("HX1.OUT_TEMP")\n\nif measured < target then\n  set("V1.OPENING", 80.0)\nelse\n  set("V1.OPENING", 65.0)\nend\n`,dirty:false};}
function sampleHistory(opening=80){return Array.from({length:81},(_,i)=>{const t=i/4,q=(1-Math.exp(-t/1.8))*3.55;const ratio=opening/(opening+55);return {t,q,a:q*ratio,b:q*(1-ratio),pressure:120+q*12,temperature:20+12*(1-Math.exp(-t/7))};});}
function initialState(){
  const modules=MODULE_SPECS.map(makeModule);
  const makeModel=(id,moduleId,name,params,description)=>({id,moduleId,name,description,version:1,params:{...defaultsFor(moduleId),...params},bank:1,archived:false,versions:[{version:1,note:'首次保存型号',params:{...defaultsFor(moduleId),...params}}]});
  return {schema:1,projects:[makeProject('water-net','泵阀并联管网','观察阀门调节后两条支路的流量分配。',waterPage()),makeProject('heat-loop','双侧换热机组','两个独立水回路与换热设备的联动示例。',heatPage()),makeProject('tank-control','水箱液位调节','容积设备、边界与调节阀的慢动态示例。',tankPage())],activeProject:'water-net',modules,
    models:[makeModel('valve-16','valve','调节阀 · Kv16',{},'标准调节阀，默认开度 80%。'),makeModel('valve-25','valve','调节阀 · Kv25',{kv:25,opening:65},'大流量型号，部分负荷工况。'),makeModel('pump-standard','pump','标准离心泵',{},'额定转速，泵效率 75%。'),makeModel('heat-standard','exchanger','板换 · UA2000',{},'一次侧与二次侧独立配置。'),makeModel('tank-5','tank','储水罐 · 5m³',{},'用于水箱液位调节场景。')],
    selectedModule:'valve',selectedModel:'valve-16',bench:{moduleId:'valve',params:defaultsFor('valve'),boundary:{inlet:201.325,outlet:120,temperature:20},run:emptyRun('bench')},
    records:[{id:'DEMO-003',name:'开度 65% · 工况对照',projectId:'water-net',projectName:'泵阀并联管网',status:'completed',mode:'慢动态',time:20,history:sampleHistory(65),params:{opening:65,kv:16},sample:true},{id:'DEMO-002',name:'额定工况 · 基准',projectId:'water-net',projectName:'泵阀并联管网',status:'completed',mode:'慢动态',time:20,history:sampleHistory(80),params:{opening:80,kv:16},sample:true},{id:'DEMO-001',name:'边界配置检查',projectId:'heat-loop',projectName:'双侧换热机组',status:'failed',mode:'稳态',time:0,history:[],params:{},sample:true}],
    charts:{series:{q:true,a:true,b:true},extra:[],compare:false,source:'live'},
    connectors:[{id:'serial1',name:'实验台串口',kind:'serial',port:'COM3',baud:'115200',connected:false},{id:'api1',name:'本地变量接口',kind:'http',port:'8765',connected:false}],
    messages:[{time:'示例',kind:'INFO',text:'已载入泵阀并联管网示例。'},{time:'示例',kind:'CHECK',text:'项目、模块、型号、控制与曲线可切换查看。'}],
    savedAt:null,dirty:false,serial:21
  };
}
