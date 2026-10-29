"""只读取冻结运行快照与已接受帧；生成报告绝不重新求解。"""
import csv
from html import escape
from io import StringIO

from .air_models import AirVariableDescriptor


def value_at(frame,key):
    return (frame.get('metrics',{}).get(key[8:]) if key.startswith('metrics.')
            else frame.get('variables',{}).get(key))


def formatted(value,descriptor,display=False):
    if value is None:
        return ''
    if isinstance(value,bool):
        return 'true' if value else 'false'
    if isinstance(value,(int,float)):
        if display and descriptor.unit:
            value=descriptor.unit.from_canonical(value)
        return format(value,'.12g')
    return str(value)


def csv_report(record,rows,decimated=False):
    metadata=record['air_metadata']
    catalog=[AirVariableDescriptor.model_validate(v) for v in metadata['variable_catalog']]
    out=StringIO(newline='');writer=csv.writer(out)
    writer.writerow(['运行ID','项目摘要','物性版本','抽稀概览','时间(s)','帧序号','参数修订','变量键','中文名称','质量基准',
                     '规范单位','规范数值','显示单位','显示数值'])
    def safe(value):
        return "'"+value if isinstance(value,str) and value.startswith(('=','+','-','@')) else value
    for frame in rows:
        for descriptor in catalog:
            if record['mode'] not in descriptor.available_in:
                continue
            value=value_at(frame,descriptor.key)
            row=[record['id'],metadata['project_snapshot_hash'],metadata['property_version'],str(decimated).lower(),
                 frame['time_s'],frame.get('sequence'),frame.get('parameter_revision'),descriptor.key,descriptor.label,
                 descriptor.mass_basis,descriptor.unit.canonical_unit if descriptor.unit else '',
                 formatted(value,descriptor),descriptor.unit.display_unit if descriptor.unit else '',formatted(value,descriptor,True)]
            # 数值列保留负号，文本列防止被电子表格解释成公式。
            writer.writerow([safe(v) if i in (0,7,8,9,10,12) else v for i,v in enumerate(row)])
    return '\ufeff'+out.getvalue()


def html_report(record,rows,decimated=False):
    metadata=record['air_metadata']
    valid=[row for row in rows if row.get('valid')]
    frame=valid[-1] if valid else rows[-1]
    table=[]
    for raw in metadata['variable_catalog']:
        v=AirVariableDescriptor.model_validate(raw)
        if record['mode'] not in v.available_in:
            continue
        value=value_at(frame,v.key)
        table.append('<tr>'+''.join('<td>'+escape(str(item))+'</td>' for item in (
            v.label,v.key,formatted(value,v,True) if value is not None else '—',
            v.unit.display_unit if v.unit else '—',v.mass_basis))+'</tr>')
    assumption=''.join('<li>'+escape(text)+'</li>' for text in metadata['assumptions'])
    warning='历史窗口已裁剪，曲线使用抽稀概览；累计量取已接受状态。' if decimated else '数据来自已保存的接受帧。'
    if record['status']!='completed':
        warning+=' 运行未完整完成；以下为最后可用帧。'
    title=escape(record['request']['project']['name'])
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>{title} · 风侧运行报告</title>
<style>body{{font:15px/1.65 system-ui,"Microsoft YaHei",sans-serif;max-width:1200px;margin:40px auto;color:#173042}}
h1{{color:#126c72}}table{{width:100%;border-collapse:collapse}}th,td{{padding:7px 10px;border-bottom:1px solid #dbe5e9;text-align:left}}
td:nth-child(2){{font:12px monospace;overflow-wrap:anywhere}}.meta{{background:#edf6f7;padding:18px;border-radius:8px}}
@media print{{body{{margin:15mm;font-size:10pt}}thead{{display:table-header-group}}tr{{break-inside:avoid}}}}</style>
<h1>{title} · 风侧运行报告</h1><div class="meta">运行 {escape(record['id'])} · 状态 {escape(record['status'])}<br>
时间 {frame['time_s']:g} s · 帧 {frame.get('sequence',0)} · 参数修订 {frame.get('parameter_revision',0)}<br>
CoolProp {escape(metadata['property_version'])} · 合同 1<br>项目摘要 {escape(metadata['project_snapshot_hash'])}</div>
<p>{warning}</p><h2>模型假设</h2><ul>{assumption}</ul><h2>状态与结果</h2>
<table><thead><tr><th>名称</th><th>变量键</th><th>数值</th><th>显示单位</th><th>质量基准</th></tr></thead>
<tbody>{''.join(table)}</tbody></table></html>'''
