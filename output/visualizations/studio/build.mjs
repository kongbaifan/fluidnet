import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import * as Lucide from 'lucide-react';

const names = ['Activity','ArrowDownToLine','ArrowRight','ArrowRightLeft','ArrowUpRight','Bell','BookOpen','Box','Boxes','Braces','Cable','Check','CheckCheck','CheckCircle2','ChevronDown','ChevronLeft','ChevronRight','Circle','CircleDot','CircleHelp','CirclePlus','Clipboard','Clock3','Code2','Columns2','Copy','Database','Download','Droplets','Ellipsis','ExternalLink','Eye','FileCode2','FileJson','FileText','Filter','Flame','Folder','FolderOpen','Gauge','GitBranch','GitCompareArrows','Grid2X2','Grip','GripVertical','History','Home','Info','Keyboard','Layers','LayoutDashboard','List','ListChecks','Lock','Maximize2','MessageSquare','Minimize2','Minus','Monitor','Moon','MoreHorizontal','MousePointer2','Move','Network','PanelLeftClose','PanelLeftOpen','Pause','Pencil','Pin','Play','Plug','Plus','Redo2','RefreshCw','RotateCcw','RotateCw','Save','Scan','Search','Settings2','ShieldCheck','SlidersHorizontal','Square','SquareDashed','Star','StepForward','Sun','Table2','Terminal','Thermometer','Trash2','Triangle','Undo2','Upload','Waypoints','Wind','Wrench','X','Zap'];
const icons = Object.fromEntries(names.map(name => {
  if (!Lucide[name]) throw new Error(`Unknown icon: ${name}`);
  return [name, renderToStaticMarkup(createElement(Lucide[name], { width:18, height:18, strokeWidth:1.65, 'aria-hidden':'true', focusable:'false' }))];
}));
const here = new URL('.', import.meta.url);
const [template, css, workbenchCss, interactionCss, pythonCode, data, app, variables, workbench, groups, canvasActions, variableFlow, runtime] = await Promise.all(['index.html','styles.css','workbench.css','interaction-details.css','python-code.js','data.js','app.js','instance-variables.js','workbench.js','module-groups.js','canvas-actions.js','variable-flow.js','runtime.js'].map(name=>readFile(new URL(name,here),'utf8')));
const script = `(() => {\n'use strict';\nconst ICONS = ${JSON.stringify(icons)};\n${pythonCode}\n${data}\n${app}\n${variables}\n${workbench}\n${groups}\n${canvasActions}\n${variableFlow}\n${runtime}\n})();`;
const html = template.replace('<!-- STUDIO_STYLES -->', `<style>\n${css}\n${workbenchCss}\n${interactionCss}\n</style>`).replace('<!-- STUDIO_SCRIPT -->', `<script>\n${script.replace(/<\/script/gi, '<\\/script')}\n</script>`);
const destination = new URL('../fluidnet-studio-prototype.html',here);
await writeFile(destination,html);
console.log(JSON.stringify({ file:fileURLToPath(destination), bytes:Buffer.byteLength(html), pages:12 }));
