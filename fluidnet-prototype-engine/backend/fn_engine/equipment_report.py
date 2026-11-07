"""General fluid-equipment reports from frozen request and accepted rows, without compilation."""
import csv
from html import escape
from io import StringIO


def fields(record, rows):
    project=record['request']['project']
    definitions={m['id']:m for m in project['modules']}
    declared={}
    for node in project['instances']:
        definition=definitions[node['module_id']]
        for v in definition.get('variables',[]):
            declared[node['id']+'.'+v['id']]=(node.get('name',node['id'])+' · '+v['label'],v.get('unit'))
        for p in definition.get('parameters',[]):
            if p.get('value_type','number')=='number':declared[node['id']+'.param.'+p['id']]=(node.get('name',node['id'])+' · '+p['label'],p.get('unit'))
    present=set().union(*(row.get('variables',{}).keys() for row in rows))
    return [(key,*declared.get(key,(key,None))) for key in sorted(present)]


def shown(value,unit):
    if value is None:return '—'
    if isinstance(value,bool):return str(value).lower()
    if isinstance(value,(float,int)):
        return format(value/unit.get('display_scale',1)+unit.get('display_offset',0) if unit else value,'.12g')
    return str(value)


def csv_report(record,rows,decimated=False):
    out=StringIO(newline='');writer=csv.writer(out)
    writer.writerow(['运行ID','时间(s)','变量键','名称','规范单位','规范值','显示单位','显示值','抽稀'])
    def safe_text(value):
        """Keep arbitrary text from being interpreted as a spreadsheet formula."""
        return "'"+value if isinstance(value,str) and value.startswith(('=','+','-','@')) else value
    for row in rows:
        for key,label,unit in fields(record,[row]):
            value=row['variables'].get(key)
            display=shown(value,unit)
            writer.writerow([safe_text(record['id']),row['time_s'],safe_text(key),safe_text(label),
                             safe_text((unit or {}).get('canonical_unit','')),safe_text(value),
                             safe_text((unit or {}).get('display_unit','')),
                             safe_text(display) if isinstance(value,str) else display,decimated])
    return '\ufeff'+out.getvalue()


def html_report(record,rows,decimated=False):
    last=rows[-1]['variables'];project=record['request']['project']
    body=''.join('<tr>'+''.join('<td>'+escape(str(v))+'</td>' for v in
        (key,label,shown(last.get(key),unit),(unit or {}).get('display_unit','未声明')) )+'</tr>' for key,label,unit in fields(record,rows))
    definitions={m['id']:m for m in project['modules']}
    assumptions=''.join('<li>'+escape(definitions[mid].get('description',''))+'</li>' for mid in sorted({n['module_id'] for n in project['instances']}))
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>设备运行报告</title>'
        '<style>body{font:14px sans-serif;margin:32px}table{border-collapse:collapse;width:100%}td,th{padding:8px;border:1px solid #ccc;text-align:left}</style>'
        '<h1>'+escape(project['name'])+'</h1><p>运行 '+escape(record['id'])+' · '+escape(record['status'])+' · t='+str(rows[-1]['time_s'])+' s</p>'
        '<p>只读取该次运行的冻结定义和已接受帧，不重新执行设备代码。'+('历史为抽稀概览。' if decimated else '')+'</p>'
        '<h2>设备模型与边界</h2><ul>'+assumptions+'</ul><h2>末帧变量</h2><table><tr><th>变量键</th><th>名称</th><th>显示值</th><th>单位</th></tr>'+body+'</table></html>')
