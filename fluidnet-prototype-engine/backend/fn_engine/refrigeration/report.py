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
    legend = ''.join(f'<span style="color:{colors[i % 4]}">■ {html.escape(label)}</span>' for i, (_, label) in enumerate(series))
    return (f'<figure><svg viewBox="0 0 680 250" role="img" aria-label="{html.escape(title)}" style="width:100%;max-width:760px">'
            f'<path d="M60 20 V210 H660" fill="none" stroke="#555"/>{"".join(paths)}'
            f'<text x="4" y="26" font-size="11">{y1:.4g}</text><text x="4" y="210" font-size="11">{y0:.4g}</text>'
            f'<text x="60" y="230" font-size="11">{t0 / 3600:.2f} h</text><text x="600" y="230" font-size="11">{t1 / 3600:.2f} h</text>'
            f'<text x="60" y="246" font-size="11">{html.escape(unit)}</text></svg>'
            f'<figcaption>{html.escape(title)}</figcaption><div class="chart-legend">{legend}</div></figure>')


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
         'vertical-align:top;overflow-wrap:anywhere}th{background:#eef2f6}pre{background:#f6f8fa;padding:10px;white-space:pre-wrap}'
         '.note{color:#5b6670}figure{margin:12px 0}.chart-legend{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:12px}')


def _scenario_name(record):
    project, sid = record['request']['project'], record['request'].get('scenario_id')
    return next((s['name'] for s in project.get('scenarios', []) if s['id'] == sid), '基础模型') if sid else '基础模型'


def _timestep_rows(rows, network):
    """A4：内部步长、拒绝数与该帧最大局部时间离散误差范数；旧档案缺失时明确标注。

    指标只描述 step-doubling 的 **局部** 时间离散误差估计，不是全程误差，也不是模型准确度保证。
    """
    options = network.project.solver.time_step
    limits = (f'{options.min_internal_step_s:g}–{options.max_internal_step_s:g} s'
              if options.max_internal_step_s is not None else f'{options.min_internal_step_s:g} s 起，上限沿用发布步长')
    settings = (f'{"开启（step-doubling 接受/拒绝）" if options.enabled else "关闭（固定步长旧路径）"}；'
                f'atol 质量 {options.mass_atol_kg:g} kg / 能量 {options.energy_atol_j:g} J / 温度 '
                f'{options.temperature_atol_k:g} K；rtol {options.rtol:g}；内部步长 {limits}')
    body = [('时间误差控制设置', html.escape(settings))]
    last = (rows[-1].get('metrics') if rows else None) or {}
    if 'timestep_adaptive' not in last:
        body.append(('内部步长 / 拒绝数 / 最大局部误差范数', '本档案没有这些指标（A4 之前的运行记录）'))
        return body
    adaptive = bool(last['timestep_adaptive'])
    accepted = last.get('internal_steps_total')
    accepted = accepted if accepted is not None else sum(int((r.get('metrics') or {}).get('internal_steps') or 0) for r in rows)
    rejected = last.get('internal_rejections_total')
    rejected = rejected if rejected is not None else sum(int((r.get('metrics') or {}).get('internal_rejections') or 0) for r in rows)
    boundary = sum(int((r.get('metrics') or {}).get('boundary_truncations') or 0) for r in rows)
    steps = [(r.get('metrics') or {}).get('internal_step_s') for r in rows]
    steps = [float(s) for s in steps if isinstance(s, (int, float)) and s > 0]
    errors = [(r.get('metrics') or {}).get('local_error_norm_max') for r in rows]
    errors = [float(e) for e in errors if isinstance(e, (int, float))]
    mode = '自适应（误差接受控制）' if adaptive else '固定步长（未开启误差接受控制）'
    body += [
        ('内部积分 / 内部步长范围', f'{mode}；被接受内部步 {accepted} 步；步长 '
                               f'{min(steps):.3g}–{max(steps):.3g} s' if steps else f'{mode}；被接受内部步 {accepted} 步'),
        ('内部步拒绝 / 边界截断', f'{rejected} 次误差拒绝 / {boundary} 次边界截断'),
        ('局部时间离散误差范数最大值', f'{max(errors):.3g}（step-doubling 局部估计；不是全程误差，也不是模型准确度保证）'
                                if errors else '无（固定步长路径不估计）'),
    ]
    return body


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
            + '<h2>时间离散误差控制</h2>' + _table(['指标', '数值'], _timestep_rows(rows, network))
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
              ('内部步长', a.project.solver.dynamic_step_s == b.project.solver.dynamic_step_s),
              ('时间误差控制设置（A0）', a.project.solver.time_step == b.project.solver.time_step)]
    return checks


# --- case B: lumped NH3/CO2 station ---------------------------------------------------------------

def station_series_keys(network):
    """Standard curves of a station run (rooms, vessel pressures/levels, actuators, controllers, energy)."""
    keys = []
    for room, cooler in network.room_coolers.items():
        keys += [(f'{room}.state.temperature_k', 'K'), (f'{room}.param.heat_input_w', 'W'), (f'{cooler}.param.fan_ratio', '1'),
                 (f'{cooler}.refrigerant_heat_w', 'W')]
    for vessel in network.vessels:
        keys += [(f'{vessel}.state.pressure_pa', 'Pa'), (f'{vessel}.state.temperature_k', 'K'), (f'{vessel}.state.level_ratio', '1')]
    for iid, kind in network.kinds.items():
        keys += {'refrigerant_compressor': [(f'{iid}.param.running', '1'), (f'{iid}.param.load_ratio', '1'), (f'{iid}.electric_power_w', 'W')],
                 'evaporative_condenser': [(f'{iid}.param.fan_ratio', '1'), (f'{iid}.param.return_gas_ratio', '1'),
                                           (f'{iid}.param.wet_bulb_temperature_k', 'K'), (f'{iid}.heat_rejection_w', 'W')],
                 'expansion_valve': [(f'{iid}.param.opening_ratio', '1'), (f'{iid}.mass_flow_kg_s', 'kg/s')],
                 'refrigerant_pump': [(f'{iid}.param.speed_ratio', '1')],
                 'cascade_exchanger': [(f'{iid}.heat_w', 'W')]}.get(kind, [])
    keys += [(f'controller.{c.id}.setpoint', '') for c in network.project.controllers]
    for iid,definition in network.refrigeration_modules.items():
        keys += [(f'{iid}.{v.id}',v.unit.canonical_unit if v.unit else '1')
                 for v in definition.variables if v.sampleable]
    return list(dict(keys).items())


def station_module_results(rows, network):
    """Contract-driven outputs and immutable version identities from this archived run."""
    if not network.refrigeration_modules:
        return ''
    from ..packages import package_ref
    versions,outputs=[],[]
    last=rows[-1]['variables']
    for iid,definition in network.refrigeration_modules.items():
        package=package_ref(definition)
        versions.append(tuple(html.escape(str(value)) for value in
            (iid,definition.id,definition.version,package.content_hash,package.definition_hash)))
        for variable in definition.variables:
            if not variable.sampleable:
                continue
            key=f'{iid}.{variable.id}'
            outputs.append((html.escape(key),html.escape(variable.label),html.escape(str(last.get(key,'—'))),
                html.escape(variable.unit.canonical_unit if variable.unit else '1')))
    return ('<h2>作者模块冻结版本</h2>'+_table(['设备','模块','版本','源码 SHA-256','定义 SHA-256'],versions)
        +'<h2>作者设备末帧结果</h2>'+_table(['变量','名称','值','规范单位'],outputs)
        +'<p class="note">以上定义、版本及结果来自本次运行快照；生成报告不执行作者代码。</p>')


def station_metrics(rows, network):
    last = rows[-1]['variables']
    counters = [k for k in last if k.endswith(('.state.electric_energy_j', '.state.fan_energy_j'))]
    electric = sum(last[k] for k in counters)
    controllers = {c.id: c for c in network.project.controllers}

    def tracking(cid, start):
        c = controllers.get(cid)
        if c is None:
            return None
        values = [abs(r['variables'][c.measurement] - r['variables'][f'controller.{cid}.setpoint']) for r in rows
                  if r['time_s'] >= start and c.measurement in r['variables']]
        return max(values) if values else None
    rooms = {}
    for room in network.room_coolers:
        pid = next((c for c in controllers.values() if c.measurement == f'{room}.state.temperature_k'), None)
        values = [r['variables'][f'{room}.state.temperature_k'] - (r['variables'][f'controller.{pid.id}.setpoint'] if pid else 255.15)
                  for r in rows if f'{room}.state.temperature_k' in r['variables']]
        rooms[room] = {'max_deviation_k': max(abs(v) for v in values), 'final_temperature_k': last[f'{room}.state.temperature_k']}
    script = lambda key: last.get(f'script.control.state.{key}')
    return {'electric_energy_j': electric, 'mean_electric_power_w': electric / max(1., rows[-1]['time_s']),
            'satisfaction': script('satisfaction'), 'compressor_starts': script('starts'), 'compressor_stops': script('stops'),
            'condenser_fan_changes': script('fan_changes'), 'last_reason': script('reason'), 'target_infeasible': script('infeasible'),
            'rooms': rooms, 'levels': {v: {'min': min(r['variables'][f'{v}.state.level_ratio'] for r in rows),
                                           'max': max(r['variables'][f'{v}.state.level_ratio'] for r in rows)} for v in network.vessels},
            'max_tracking_after_1h': {cid: tracking(cid, 3600.) for cid in controllers},
            'energy_residual_j': rows[-1]['metrics']['energy_residual_j'],
            'mass_residual_kg': {k: rows[-1]['metrics'][k] for k in rows[-1]['metrics'] if k.startswith('mass_residual_kg')},
            'events_applied': rows[-1]['metrics'].get('events_applied'), 'initial_electric_power_w': rows[0]['metrics'].get('electric_power_w'),
            'final_electric_power_w': rows[-1]['metrics'].get('electric_power_w')}


def station_csv(rows, network):
    keys = station_series_keys(network)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\r\n')
    writer.writerow(['time_s'] + [f'{key} [{unit}]' if unit else key for key, unit in keys])
    for row in rows:
        values = row['variables']
        writer.writerow([row['time_s']] + ['' if values.get(key) is None else values[key] for key, _ in keys])
    return BOM + buffer.getvalue()


def station_report(record, rows, network):
    m = station_metrics(rows, network)
    rooms = list(network.room_coolers)
    pct = lambda v: '—' if v is None else f'{v * 100:.2f} %'
    body = [('需求满足度（库温在设定 ±1 K 内的时间占比，自定义口径）', pct(m['satisfaction'])),
            ('制冷站电量（压缩机、液泵、冷凝器与冷风机风机）', _text(m['electric_energy_j'], 'kWh')),
            ('平均电功率 / 末帧电功率', f'{_text(m["mean_electric_power_w"], "kW")} / {_text(m["final_electric_power_w"], "kW")}'),
            ('压缩机启动 / 停止次数', f'{_text(m["compressor_starts"], "", 0)} / {_text(m["compressor_stops"], "", 0)}'),
            ('冷凝器风机组切换次数', _text(m['condenser_fan_changes'], '', 0)),
            ('最后一次上层动作', html.escape(str(m['last_reason']))),
            ('目标冷凝压力不可达', '是' if m['target_infeasible'] else '否'),
            *[(f'{r} 最大偏离设定 / 末态库温', f'{_text(v["max_deviation_k"], "K")} / {_text(v["final_temperature_k"], "C")}') for r, v in m['rooms'].items()],
            *[(f'{v} 液位范围', f'{x["min"]:.4f} … {x["max"]:.4f}') for v, x in m['levels'].items()],
            *[(f'控制器 {cid} 1 h 后最大跟踪偏差', '—' if v is None else f'{v:.4g}') for cid, v in m['max_tracking_after_1h'].items()],
            *_timestep_rows(rows, network),
            ('能量账本残差', _text(m['energy_residual_j'], 'J')),
            ('回路存量残差', html.escape(', '.join(f'{k}={v:.3g} kg' for k, v in m['mass_residual_kg'].items())))]
    pressure_targets=[(c.measurement,f'{c.id} · 测量') for c in network.project.controllers if c.measurement.endswith('.state.pressure_pa')]
    pressure_targets += [(f'controller.{c.id}.setpoint',f'{c.id} · 设定') for c in network.project.controllers if c.measurement.endswith('.state.pressure_pa')]
    if not pressure_targets:pressure_targets=[(f'{v}.state.pressure_pa',v) for v in network.vessels]
    actuator_targets=[]
    for iid,kind in network.kinds.items():
        for suffix,label in {'refrigerant_compressor':[('load_ratio','载量')],
            'evaporative_condenser':[('fan_ratio','风机'),('return_gas_ratio','回气阀')],
            'expansion_valve':[('opening_ratio','开度')]}.get(kind,[]):
            actuator_targets.append((f'{iid}.param.{suffix}',f'{iid} · {label}'))
    charts = (_chart(rows, [(f'{r}.state.temperature_k', r) for r in rooms], '库温', '°C', offset=-273.15)
              + _chart(rows, pressure_targets, '容器压力与控制目标', 'kPa', scale=1000.)
              + _chart(rows, [(f'{v}.state.level_ratio', v) for v in network.vessels], '容器液位', '1')
              + _chart(rows, actuator_targets, '执行器', '1'))
    events = _table(['ID', '时刻', '写入'], [(html.escape(e.id), f'{e.time_s / 3600:.3f} h', html.escape(f'{e.key} = {e.value:g}'))
                                         for e in network.events]) if network.events else '<p>本次运行没有日程事件。</p>'
    request = record['request']
    return (f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>制冷站运行报告</title><style>{STYLE}</style></head>'
            '<body><h1>制冷站运行报告</h1>'
            + _table(['项目', '内容'], [('项目', html.escape(request['project']['name'])), ('工况', html.escape(_scenario_name(record))),
                                       ('运行', html.escape(record['id'])), ('状态', html.escape(record['status'])),
                                       ('项目修订', html.escape(str(request.get('project_revision') or '未保存草稿'))),
                                       ('仿真时长 / 发布间隔', f'{rows[-1]["time_s"] / 3600:.3f} h / {request["dt_s"]:g} s'),
                                       ('引擎版本', __version__), ('数据等级', '工程示范假设；不与倍思鹿数值对比')])
            + '<h2>指标</h2>' + _table(['指标', '数值'], body) + charts + station_module_results(rows,network) + '<h2>日程</h2>' + events
            + '<h2>模型边界</h2><p>集总制冷站：压力只在饱和容器中，其余设备为代数关系；不计管路压降、换热器持液与过冷/过热；'
              '单级压缩未计油冷，排气温度偏高。控制：吸气压力→压缩机载量、贮液器压力→回气阀、贮液器液位→节流阀、库温→冷风机风量，'
              '上层脚本按载量增减压缩机、按回气阀开度增减冷凝器风机组、按冷风机风量调液泵。</p></body></html>')


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
