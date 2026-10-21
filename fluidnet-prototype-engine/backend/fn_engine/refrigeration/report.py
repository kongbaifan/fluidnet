"""Cold-store run metrics, CSV export and HTML report, computed from archived frames only.

Cumulative quantities come from the exact `state.*` counters of the final frame; peaks and recovery
times are read from published frames (resolution = publish interval) and labelled as such.
"""
import csv
import html
import io
import math

from .. import __version__

BOM = chr(0xFEFF)  # lets spreadsheet programs detect UTF-8

ROOM_KEYS = [('state.temperature_k', 'K'), ('state.goods_temperature_k', 'K'), ('state.goods_mass_kg', 'kg'),
             ('param.setpoint_temperature_k', 'K'), ('envelope_heat_w', 'W'), ('door_heat_w', 'W'), ('goods_heat_w', 'W'),
             ('fan_heat_w', 'W'), ('defrost_heat_w', 'W'), ('cooling_power_w', 'W'), ('stored_energy_j', 'J'),
             ('state.external_energy_j', 'J'), ('state.cooling_energy_j', 'J')]
COOLER_KEYS = [('state.mode', '1'), ('state.fan_running', '1'), ('fan_power_w', 'W'), ('heater_power_w', 'W'),
               ('state.fan_energy_j', 'J'), ('state.heater_energy_j', 'J')]
UNIT_KEYS = [('state.running', '1'), ('actual_capacity_ratio', '1'), ('param.ambient_temperature_k', 'K'),
             ('evaporating_temperature_k', 'K'), ('condensing_temperature_k', 'K'), ('evaporating_pressure_pa', 'Pa'),
             ('condensing_pressure_pa', 'Pa'), ('suction_temperature_k', 'K'), ('discharge_temperature_k', 'K'),
             ('pressure_ratio', '1'), ('mass_flow_kg_s', 'kg/s'), ('cooling_power_w', 'W'), ('shaft_power_w', 'W'),
             ('electric_power_w', 'W'), ('condenser_heat_w', 'W'), ('condenser_fan_power_w', 'W'), ('cop', '1'),
             ('system_cop', '1'), ('state.starts', '1'), ('state.run_time_s', 's'), ('state.electric_energy_j', 'J')]


def series_keys(chains):
    """Frame variables of the standard curves and CSV columns; pass them as `trend_variables`."""
    keys = []
    for unit, cooler, room in chains:
        keys += [(f'{room}.{k}', u) for k, u in ROOM_KEYS] + [(f'{cooler}.{k}', u) for k, u in COOLER_KEYS]
        keys += [(f'{unit}.{k}', u) for k, u in UNIT_KEYS]
    return keys


def _event_window(event, cooler_params):
    if event['type'] == 'door_heat':
        return event['time_s'] + event['duration_s']
    if event['type'] == 'electric_defrost':
        return event['time_s'] + cooler_params['defrost_duration_s'] + cooler_params['drip_duration_s']
    return event['time_s']


def run_metrics(record, rows, network):
    """Per-room indicators of one run (canonical units)."""
    project, last, first = network.project, rows[-1]['variables'], rows[0]['variables']
    results = []
    for unit, cooler, room in network.chains:
        p_room, p_cooler = network.parameters[room], network.parameters[cooler]
        get = lambda key: last.get(key)
        setpoint, band = last[f'{room}.param.setpoint_temperature_k'], last[f'{room}.param.hysteresis_k']
        electric = {'compressor': get(f'{unit}.state.electric_energy_j'),
                    'condenser_fan': get(f'{unit}.state.condenser_fan_energy_j'),
                    'cooler_fan': get(f'{cooler}.state.fan_energy_j'), 'defrost_heater': get(f'{cooler}.state.heater_energy_j')}
        total = sum(electric.values())
        cooling = get(f'{unit}.state.cooling_energy_j')
        high, low = get(f'{room}.state.max_service_temperature_k'), get(f'{room}.state.min_service_temperature_k')
        # Independent ledger from published counters: ΔE_stored = E_in + E_goods + E_fan + f·E_heater − E_coil.
        fraction = p_cooler['defrost_room_fraction']
        inflow = (get(f'{room}.state.external_energy_j') + get(f'{room}.state.goods_energy_j') + electric['cooler_fan']
                  + fraction * electric['defrost_heater'])
        outflow = get(f'{room}.state.cooling_energy_j')
        stored = get(f'{room}.stored_energy_j') - first[f'{room}.stored_energy_j']
        events = []
        for event in project.events:
            if event.time_s >= rows[-1]['time_s'] or event.type == 'ambient_temperature':
                continue
            # Door/defrost: room peak and time after the event until the room is back inside the start band.
            # Goods: goods-node peak and time until the goods are back at their pre-event temperature.
            key = f'{room}.state.goods_temperature_k' if event.type == 'goods_addition' else f'{room}.state.temperature_k'
            series = [(r['time_s'], r['variables'].get(key)) for r in rows if r['variables'].get(key) is not None]
            before = [value for t, value in series if t <= event.time_s]
            end = _event_window(event.model_dump(), p_cooler)
            limit = before[-1] if event.type == 'goods_addition' and before else setpoint + band
            recovered = next((t for t, value in series if t > end and value <= limit + 1e-9), None)
            window = [value for t, value in series if event.time_s < t <= (recovered if recovered is not None else math.inf)]
            events.append({'id': event.id, 'type': event.type, 'time_s': event.time_s, 'end_s': end, 'variable': key,
                           'recovery_limit_k': limit, 'peak_k': max(window) if window else None,
                           'recovery_s': recovered - end if recovered is not None else None})
        results.append({
            'room': room, 'cooler': cooler, 'unit': unit, 'setpoint_temperature_k': setpoint, 'hysteresis_k': band,
            'alarm_temperature_k': last[f'{room}.param.alarm_temperature_k'],
            'final_room_temperature_k': get(f'{room}.state.temperature_k'),
            'final_goods_temperature_k': get(f'{room}.state.goods_temperature_k'),
            'final_goods_mass_kg': get(f'{room}.state.goods_mass_kg'),
            'pulldown_time_s': get(f'{room}.state.pulldown_time_s'), 'goods_pulldown_time_s': get(f'{room}.state.goods_pulldown_time_s'),
            'max_service_temperature_k': high, 'min_service_temperature_k': low,
            'max_service_deviation_k': max(high - setpoint, setpoint - low) if high is not None else None,
            'time_above_alarm_s': get(f'{room}.state.time_above_alarm_s'),
            'degree_hours_above_alarm': get(f'{room}.state.degree_hours_above_alarm'),
            'service_time_above_alarm_s': get(f'{room}.state.service_time_above_alarm_s'),
            'service_degree_hours_above_alarm': get(f'{room}.state.service_degree_hours_above_alarm'),
            'starts': get(f'{unit}.state.starts'), 'run_time_s': get(f'{unit}.state.run_time_s'),
            'electric_energy_j': electric, 'total_electric_energy_j': total,
            'lighting_energy_j': get(f'{room}.state.lighting_energy_j'),
            'cooling_energy_j': cooling, 'condenser_heat_j': get(f'{unit}.state.condenser_heat_j'),
            'period_cop': cooling / total if total > 0 else None,
            'stored_energy_change_j': stored, 'final_stored_energy_j': get(f'{room}.stored_energy_j'),
            'ledger_residual_j': stored - (inflow - outflow), 'ledger_scale_j': inflow + outflow,
            'events': events, 'goods_mass_kg_initial': p_room['goods_mass_kg']})
    return results


def run_csv(rows, network):
    """Time series of the standard curves (canonical units); empty cells where a frame does not carry a key."""
    keys = series_keys(network.chains)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\r\n')
    writer.writerow(['time_s'] + [f'{key} [{unit}]' for key, unit in keys])
    for row in rows:
        values = row['variables']
        writer.writerow([row['time_s']] + ['' if values.get(key) is None else values[key] for key, _ in keys])
    return BOM + buffer.getvalue()


def _text(value, kind='', digits=3):
    if value is None:
        return '—'
    if isinstance(value, float) and not math.isfinite(value):
        return '—'
    scale = {'C': lambda v: f'{v - 273.15:.{digits}f} °C', 'K': lambda v: f'{v:.{digits}f} K',
             'kWh': lambda v: f'{v / 3.6e6:.{digits}f} kWh', 'h': lambda v: f'{v / 3600:.{digits}f} h',
             'min': lambda v: f'{v / 60:.{digits}f} min', 'kW': lambda v: f'{v / 1000:.{digits}f} kW',
             'Kh': lambda v: f'{v:.{digits}f} K·h', 'J': lambda v: f'{v:.{digits}g} J'}
    return scale[kind](value) if kind in scale else (f'{value:.{digits}f}' if isinstance(value, float) else str(value))


def _chart(rows, series, title, unit, scale=1., offset=0.):
    """Inline SVG polyline; None values (unit off) break the line."""
    points = [(r['time_s'], [r['variables'].get(key) for key, _ in series]) for r in rows]
    values = [v / scale + offset for _, vs in points for v in vs if v is not None]
    if not values:
        return f'<p>{html.escape(title)}：无数据</p>'
    t0, t1 = points[0][0], max(points[-1][0], points[0][0] + 1)
    y0, y1 = min(values), max(values)
    span = max(y1 - y0, 1e-9)
    colors = ['#2279bd', '#ce6b13', '#3b8a3e', '#8a3b8a']
    paths = []
    for index, (_, label) in enumerate(series):
        segments, current = [], []
        for t, vs in points:
            v = vs[index]
            if v is None:
                if current:
                    segments.append(current)
                current = []
                continue
            current.append(f'{60 + (t - t0) / (t1 - t0) * 600:.1f},{210 - ((v / scale + offset) - y0) / span * 180:.1f}')
        if current:
            segments.append(current)
        paths += [f'<polyline fill="none" stroke="{colors[index % 4]}" stroke-width="1.6" points="{" ".join(s)}"/>' for s in segments]
    legend = ''.join(f'<tspan fill="{colors[i % 4]}" dx="12">■ {html.escape(label)}</tspan>' for i, (_, label) in enumerate(series))
    return (f'<figure><svg viewBox="0 0 680 250" role="img" aria-label="{html.escape(title)}" style="width:100%;max-width:760px">'
            f'<path d="M60 20 V210 H660" fill="none" stroke="#555"/>{"".join(paths)}'
            f'<text x="4" y="26" font-size="11">{y1:.4g}</text><text x="4" y="210" font-size="11">{y0:.4g}</text>'
            f'<text x="60" y="230" font-size="11">{t0 / 3600:.2f} h</text><text x="600" y="230" font-size="11">{t1 / 3600:.2f} h</text>'
            f'<text x="60" y="246" font-size="11">{html.escape(unit)}{legend}</text></svg>'
            f'<figcaption>{html.escape(title)}</figcaption></figure>')


FORMULAS = '''库房   C_r·dT_r/dt = ΣUA_i(T_边界,i − T_r) + Q_门 + Q_照明 + Q_其他 + P_风机 + f·P_融霜 + UA_g(T_g − T_r) − Q_冷风机
货物   C_g·dT_g/dt = −UA_g(T_g − T_r)，UA_g = UA_g0·M/M0；入库按同类冻结物能量加权混合
冷风机 Q_冷风机 = UA_e·(T_r − T_蒸发)，机组停机、融霜或滴水时为 0
循环   1 吸气 = (p_蒸发, T_蒸发 + 过热度)；h2 = h1 + (h2s − h1)/η_is；3 = (p_冷凝, T_冷凝 − 过冷度)；h4 = h3
       m = V_disp·容量·η_vol·ρ1；Q_蒸发 = m(h1 − h3)；P_轴 = m(h2 − h1)；Q_冷凝 = m(h2 − h3)；P_电 = P_轴/η_电机
耦合   Q_冷风机 = Q_蒸发，UA_c·(T_冷凝 − T_室外) = Q_冷凝；与库房隐式 Euler 同一牛顿迭代
设计   V_disp、UA_c 在额定点（额定制冷量、蒸发/冷凝/环境温度）反算一次后固定，不随时间步缩放'''

ASSUMPTIONS = ['参数为工程示范假设（cases/cold-storage/single-room-minus18/parameters.json），无厂家或现场数据；结果不代表具体机组选型精度。',
               '常数等熵/容积/电机效率；电机损耗排向机组外部，不进入制冷剂冷凝负荷。',
               '过热在蒸发器内完成；库温与蒸发温度差小于过热度时给出 CYCLE_SUPERHEAT_APPROACH 警告（此时偏乐观）。',
               '货物只计冻结状态显热，不计冻结潜热、呼吸热、湿度与结霜；开门为声明时长的等效附加热负荷。',
               '电融霜为预定日程：加热时停机停风机，热量按声明比例进入库房；不计霜量和融霜完成程度。',
               '忽略制冷剂管路压降、制冷剂存量与容器动态；超出声明运行范围时停止运行并给出 REFRIGERATION_ENVELOPE。']


def _table(head, body):
    return ('<table><thead><tr>' + ''.join(f'<th>{html.escape(h)}</th>' for h in head) + '</tr></thead><tbody>'
            + ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in row) + '</tr>' for row in body) + '</tbody></table>')


def _metric_rows(m):
    e = m['electric_energy_j']
    return [('库温设定 / 回差', f'{_text(m["setpoint_temperature_k"], "C", 2)} / ±{m["hysteresis_k"]:g} K'),
            ('末态库温 / 货温', f'{_text(m["final_room_temperature_k"], "C")} / {_text(m["final_goods_temperature_k"], "C")}'),
            ('降温到设定值用时 / 货温到报警线用时', f'{_text(m["pulldown_time_s"], "h")} / {_text(m["goods_pulldown_time_s"], "h")}'),
            ('保温期库温范围', f'{_text(m["min_service_temperature_k"], "C")} … {_text(m["max_service_temperature_k"], "C")}'),
            ('保温期最大偏离设定值', _text(m['max_service_deviation_k'], 'K')),
            ('超温时间 / 度时（全程）', f'{_text(m["time_above_alarm_s"], "h")} / {_text(m["degree_hours_above_alarm"], "Kh")}'),
            ('超温时间 / 度时（保温期）', f'{_text(m["service_time_above_alarm_s"], "h")} / {_text(m["service_degree_hours_above_alarm"], "Kh")}'),
            ('开机次数 / 累计运行', f'{_text(m["starts"], "", 0)} / {_text(m["run_time_s"], "h")}'),
            ('累计制冷量', _text(m['cooling_energy_j'], 'kWh')),
            ('制冷系统电量（压缩机/冷凝风机/冷风机风机/融霜）',
             f'{_text(m["total_electric_energy_j"], "kWh")}（{_text(e["compressor"], "kWh")} / {_text(e["condenser_fan"], "kWh")} / '
             f'{_text(e["cooler_fan"], "kWh")} / {_text(e["defrost_heater"], "kWh")}）'),
            ('照明电量（不计入制冷系统）', _text(m['lighting_energy_j'], 'kWh')),
            ('周期 COP（累计制冷量 / 制冷系统电量）', _text(m['period_cop'], '', 3)),
            ('库房+货物储能变化（相对初态）', _text(m['stored_energy_change_j'], 'kWh')),
            ('独立能量账本残差 / 交换规模', f'{_text(m["ledger_residual_j"], "J")} / {_text(m["ledger_scale_j"], "kWh")}')]


STYLE = ('body{font-family:system-ui,"Microsoft YaHei",sans-serif;max-width:980px;margin:24px auto;padding:0 16px;color:#1d2733}'
         'table{border-collapse:collapse;width:100%;margin:8px 0 16px}th,td{border:1px solid #c9d1d9;padding:4px 8px;text-align:left;'
         'vertical-align:top}th{background:#eef2f6}pre{background:#f6f8fa;padding:10px;white-space:pre-wrap}'
         '.note{color:#5b6670}figure{margin:12px 0}')


def _scenario_name(record):
    project, sid = record['request']['project'], record['request'].get('scenario_id')
    return next((s['name'] for s in project.get('scenarios', []) if s['id'] == sid), '基础模型') if sid else '基础模型'


def _parameters(network):
    body = []
    for iid, kind in network.kinds.items():
        definition = network.modules[network.instances[iid].module_id]
        for spec in definition.parameters:
            value = network.parameters[iid][spec.id]
            shown = spec.unit.from_canonical(value) if spec.unit else value
            body.append((html.escape(iid), html.escape(spec.label), f'{shown:.6g} {html.escape(spec.unit.display_unit if spec.unit else "")}'))
    return _table(['设备', '参数', '数值（显示单位）'], body)


def _events(network):
    if not network.events:
        return '<p>本次运行没有日程事件。</p>'
    labels = {'door_heat': '开门热负荷', 'goods_addition': '货物入库', 'ambient_temperature': '室外温度变化', 'electric_defrost': '电融霜'}
    body = [(html.escape(e.id), labels[e.type], f'{e.time_s / 3600:.3f} h', html.escape('、'.join(network.targets[e.id])),
             html.escape(', '.join(f'{k}={v:g}' for k, v in e.model_dump().items()
                                   if k in ('duration_s', 'heat_w', 'mass_kg', 'temperature_k') and v is not None)))
            for e in network.events]
    return _table(['ID', '类型', '时刻', '设备', '数值（规范单位）'], body)


def _event_metrics(m):
    if not m['events']:
        return ''
    body = [(html.escape(e['id']), html.escape(e['variable']), _text(e['peak_k'], 'C'), _text(e['recovery_limit_k'], 'C'),
             _text(e['recovery_s'], 'min', 1) if e['recovery_s'] is not None else '运行结束前未恢复') for e in m['events']]
    return ('<h3>扰动与恢复</h3>' + _table(['事件', '观察变量', '峰值', '恢复判据（≤）', '事件结束后恢复用时'], body)
            + '<p class="note">峰值与恢复时间按发布帧读取，分辨率为发布间隔；开门/融霜看库温回到启动线，入库看货温回到入库前温度。</p>')


def run_report(record, rows, network):
    metrics = run_metrics(record, rows, network)
    request, frame = record['request'], record.get('frame') or {}
    sections = []
    for m in metrics:
        room, unit, cooler = m['room'], m['unit'], m['cooler']
        sections.append(f'<h2>{html.escape(room)} · 指标</h2>' + _table(['指标', '数值'], _metric_rows(m)) + _event_metrics(m)
            + _chart(rows, [(f'{room}.state.temperature_k', '库温'), (f'{room}.state.goods_temperature_k', '货温'),
                            (f'{room}.param.setpoint_temperature_k', '设定值')], '库温、货温与设定值', '°C', offset=-273.15)
            + _chart(rows, [(f'{unit}.cooling_power_w', '制冷量'), (f'{unit}.electric_power_w', '压缩机电功率'),
                            (f'{cooler}.heater_power_w', '融霜电功率')], '制冷量与电功率', 'kW', scale=1000.)
            + _chart(rows, [(f'{unit}.evaporating_temperature_k', '蒸发温度'), (f'{unit}.condensing_temperature_k', '冷凝温度'),
                            (f'{unit}.discharge_temperature_k', '排气温度')], '蒸发、冷凝与排气温度（停机断线）', '°C', offset=-273.15))
    codes = {}
    for row in rows:
        for d in row.get('diagnostics', []):
            codes[(d['code'], d['severity'])] = codes.get((d['code'], d['severity']), 0) + 1
    final = ''.join(f'<li>{html.escape(d["code"])}：{html.escape(d["message"])}</li>' for d in frame.get('diagnostics', [])
                    if d.get('severity') == 'error')
    return (f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>冷库运行报告 · {html.escape(request["project"]["name"])}</title>'
            f'<style>{STYLE}</style></head><body><h1>冷库运行报告</h1>'
            + _table(['项目', '内容'], [('项目', html.escape(request['project']['name'])), ('工况', html.escape(_scenario_name(record))),
                     ('运行', html.escape(record['id'])), ('状态', html.escape(record['status'])),
                     ('仿真时长 / 发布间隔 / 内部最大步长', f'{rows[-1]["time_s"] / 3600:.3f} h / {request["dt_s"]:g} s / '
                      f'{network.project.solver.dynamic_step_s:g} s'),
                     ('工质 / 物性后端', f'{html.escape(network.project.fluid.fluid)} / CoolProp'),
                     ('引擎版本', __version__), ('项目修订', html.escape(str(request.get('project_revision') or '未保存草稿'))),
                     ('数据等级', '工程示范假设；无厂家或现场数据')])
            + (f'<h2>运行停止</h2><ul>{final}</ul>' if final else '')
            + ''.join(sections)
            + '<h2>模型与公式</h2><pre>' + html.escape(FORMULAS) + '</pre><h2>假设与边界</h2><ul>'
            + ''.join(f'<li>{html.escape(a)}</li>' for a in ASSUMPTIONS) + '</ul>'
            + '<h2>日程事件</h2>' + _events(network) + '<h2>输入参数</h2>' + _parameters(network)
            + '<h2>诊断统计（已保存帧；与前一关键帧相同的重复诊断不计）</h2>' + _table(['诊断码', '级别', '帧数'], [(html.escape(c), s, n) for (c, s), n in sorted(codes.items())])
            + '<p class="note">累计量取最后一帧的精确计数；曲线与峰值来自发布帧。验证结果见案例目录 VALIDATION 文档。</p></body></html>')


def fairness(networks, records):
    """PLAN 5.2: two strategies must share model, initial state, schedule, weather, duration and sampling."""
    a, b = networks
    control = {'variable_capacity', 'capacity_ratio', 'run_request'}
    def strip(network):
        return {iid: {k: v for k, v in p.items() if k not in control} for iid, p in network.parameters.items()}
    checks = [('设备参数（不含控制方式与容量请求）', strip(a) == strip(b)),
              ('模块定义', [m.model_dump() for m in a.project.modules] == [m.model_dump() for m in b.project.modules]),
              ('日程事件', [e.model_dump() for e in a.events] == [e.model_dump() for e in b.events]),
              ('控制脚本', [s.model_dump() for s in a.project.control_scripts] == [s.model_dump() for s in b.project.control_scripts]),
              ('工质', a.project.fluid == b.project.fluid),
              ('仿真时长与发布间隔', (records[0]['request']['duration_s'], records[0]['request']['dt_s'])
               == (records[1]['request']['duration_s'], records[1]['request']['dt_s'])),
              ('内部步长', a.project.solver.dynamic_step_s == b.project.solver.dynamic_step_s)]
    return checks


def comparison_report(records, rows, networks):
    metrics = [run_metrics(r, rw, n) for r, rw, n in zip(records, rows, networks)]
    checks = fairness(networks, records)
    fair = all(ok for _, ok in checks) and all(r['status'] == 'completed' for r in records)
    body, verdicts = [], []
    for ma, mb in zip(*metrics):
        rows_ = [(label, value_a, value_b) for (label, value_a), (_, value_b) in zip(_metric_rows(ma), _metric_rows(mb))]
        body.append(f'<h2>{html.escape(ma["room"])}</h2>' + _table(['指标', 'A', 'B'], rows_))
        held = all(m['pulldown_time_s'] is not None and (m['service_time_above_alarm_s'] or 0) <= 60 for m in (ma, mb))
        scale = max(ma['cooling_energy_j'], mb['cooling_energy_j'], 1.)
        storage_gap = abs(ma['final_stored_energy_j'] - mb['final_stored_energy_j'])
        if not fair:
            verdicts.append('两次运行的模型、日程或采样设置不一致，不计算节电率。')
        elif not held:
            verdicts.append('至少一个方案保温期超温超过 60 s 或未进入保温，按约束不满足报告，不计算节电率。')
        elif storage_gap > .01 * scale:
            verdicts.append(f'末态储能相差 {storage_gap / 3.6e6:.3f} kWh（超过累计制冷量的 1%），少耗电可能来自少降温，不计算节电率。')
        else:
            ea, eb = ma['total_electric_energy_j'], mb['total_electric_energy_j']
            verdicts.append(f'温度约束满足、末态储能差 {storage_gap / 3.6e6:.3f} kWh（≤ 1% 累计制冷量）：B 相对 A 的制冷系统电量变化 '
                            f'{(eb - ea) / ea * 100:+.2f}%（{(eb - ea) / 3.6e6:+.3f} kWh）。结果可以是“无优势”，不预设节能。')
    head = _table(['', 'A', 'B'], [('运行', html.escape(records[0]['id']), html.escape(records[1]['id'])),
                                    ('工况', html.escape(_scenario_name(records[0])), html.escape(_scenario_name(records[1]))),
                                    ('状态', records[0]['status'], records[1]['status'])])
    fairness_table = _table(['公平性检查', '结果'], [(html.escape(label), '一致' if ok else '<strong>不一致</strong>') for label, ok in checks])
    return (f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>冷库控制策略对照</title><style>{STYLE}</style></head>'
            '<body><h1>冷库控制策略对照</h1>' + head + '<h2>公平性</h2>' + fairness_table
            + '<h2>结论</h2><ul>' + ''.join(f'<li>{html.escape(v)}</li>' for v in verdicts) + '</ul>' + ''.join(body)
            + '<p class="note">节电率只在两方案满足同一温度约束、末态储能可比时给出；分母为 A 的制冷系统电量。</p></body></html>')
