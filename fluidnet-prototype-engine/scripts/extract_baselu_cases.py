#!/usr/bin/env python3
"""从倍思鹿工程数据库提取参考算例快照（v0）。

只读 ``AlgProject/<project>/<project>_DB.PJTDB`` 与 ``AlgModule/<module>/<module>.cpp``，
把每个 MOD 对象的变量键集合与模块根 .cpp 中 ``void runing()`` 之前的全局变量声明做
Jaccard 匹配，然后挑出覆盖不同设备族的 10 个算例写入 ``tests/fixtures/baselu``。

本脚本不运行倍思鹿程序，也不解释加密的 ``.Modu`` 文件；输出仅代表 PJTDB 中已保存的
变量快照，不能保证是收敛后结果。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT.parents[1] / "倍思鹿数值仿真-V5.3"
DEFAULT_OUT = PROJECT_ROOT / "tests" / "fixtures" / "baselu"

PROJECT_ORDER = ("NH3CO2ZL", "ASDFGHJ")
PROVENANCE = "PJTDB snapshot; 未运行倍思鹿"

_DECL_TYPE_RE = re.compile(
    r"^\s*(?:const\s+|static\s+|volatile\s+)*"
    r"(?:double|int|float|long|short|unsigned|signed|DWORD|INT|UINT|BYTE)\b(.*)$",
    re.S,
)
_RUNING_RE = re.compile(r"\bvoid\s+runing\s*\(")
_ARRAY_WRAPPER_RE = re.compile(r"Ary(?:Double|Int)\d+")


@dataclass(frozen=True)
class ModuleSignature:
    """一个根 .cpp 在 ``void runing()`` 之前的全局变量名集合。"""

    name: str
    variables: frozenset[str]
    source: Path


@dataclass(frozen=True)
class Match:
    """MOD 键集合与模块签名的匹配结果。"""

    module: str
    score: float
    coverage: float
    missing: tuple[str, ...]
    extra: tuple[str, ...]
    ties: tuple[str, ...]
    key_count: int


@dataclass(frozen=True)
class CaseSpec:
    """一个参考算例的选型条件。"""

    project: str
    module: str
    family: str
    purpose: str


CASE_PLAN: tuple[CaseSpec, ...] = (
    CaseSpec("NH3CO2ZL", "管道通用", "pipe", "单相管道水力/热力快照，可作管网边界与初值"),
    CaseSpec("NH3CO2ZL", "截止阀", "valve", "阀门开度与阻力特性快照，覆盖 32 键的阀类契约"),
    CaseSpec("NH3CO2ZL", "泵曲线法", "pump", "泵曲线法水力快照，可作泵扬程/流量边界对照"),
    CaseSpec("NH3CO2ZL", "压缩机", "compressor", "压缩机转速/功率快照，可作强制流量与轴功初值"),
    CaseSpec("NH3CO2ZL", "冷库库房", "cold-store", "冷库库房热力状态快照，覆盖大键集与房间边界"),
    CaseSpec("NH3CO2ZL", "罐体卧式", "tank", "卧式罐体液位/压力状态快照，可作储罐初值"),
    CaseSpec("NH3CO2ZL", "管壳式换热器", "heat-exchanger", "管壳式换热器 H_in/H_out/H_metal 快照"),
    CaseSpec("ASDFGHJ", "电池", "battery", "电路电池端口快照，覆盖 45 键的多端口状态"),
    CaseSpec("ASDFGHJ", "电阻", "resistor", "电阻 U/i 状态快照，覆盖最简电路契约"),
    CaseSpec("ASDFGHJ", "电感", "inductor", "电感动态状态快照，覆盖 32 键的电路契约"),
)

# 这些名字在倍思鹿模块里通常由 runing() 计算后回写；仅作启发式标注，
# 不代表本次快照已经收敛或经过校验。
_COMPUTED_NAMES = frozenset(
    {
        "RLS",
        "CV",
        "DENSITY",
        "RE",
        "FLOW_VOLUME",
        "FLOW_SPD",
        "DHIGH",
        "MID_PRE",
        "PL",
        "TRANSFER",
        "H_out",
        "H_metal",
        "H_in",
        "H_LAST",
        "D_T",
        "Dpre",
        "COP",
    }
)
_COMPUTED_SUFFIXES = ("_U", "_i", "_Phase", "_WI")
# 罐体/冷库的 BKT_* 中，LH/LL/LW 是几何尺寸输入，其余是液位与热力状态量。
_STATE_NAMES = frozenset(
    {
        "BKT_PRE",
        "BKT_SR",
        "BKT_SL",
        "BKT_DL",
        "BKT_DV",
        "BKT_M",
        "BKT_H",
        "BKT_V",
        "BKT_D",
        "BKT_LEVEL",
        "BKT_TEMP",
        "BKT_Q",
    }
)


def _strip_function_bodies(text: str) -> str:
    """删除 ``) { ... }`` 形式的函数体，避免把局部变量当成全局声明。"""

    while True:
        match = re.search(r"\)\s*\{", text)
        if match is None:
            return text
        start = text.index("{", match.start())
        depth = 0
        end: int | None = None
        for index in range(start, len(text)):
            char = text[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end is None:
            return text
        text = text[: match.start() + 1] + text[end:]


def _split_top_level(text: str, separator: str) -> list[str]:
    """按分隔符切分，忽略括号内部的逗号。"""

    parts: list[str] = []
    buffer: list[str] = []
    depth = 0
    for char in text:
        if char in "([":
            depth += 1
        elif char in ")]":
            depth = max(0, depth - 1)
        if char == separator and depth == 0:
            parts.append("".join(buffer))
            buffer = []
        else:
            buffer.append(char)
    parts.append("".join(buffer))
    return parts


def parse_module_signature(cpp_path: Path) -> ModuleSignature:
    """解析 ``void runing()`` 之前的全局变量名。

    支持 ``double a = 0.0;``、``double arr[8] = {0.0};``、``int x = 0;`` 以及
    逗号分隔的多声明；通过先移除函数体来排除 ``SetDllDirectoryABCDEFG()`` 内的
    ``mid_Path`` / ``nbsum`` 等局部变量。
    """

    text = cpp_path.read_text(encoding="utf-8-sig", errors="replace")
    match = _RUNING_RE.search(text)
    head = text[: match.start()] if match else text
    head = _strip_function_bodies(head)
    head = re.sub(r"/\*.*?\*/", "", head, flags=re.S)
    head = re.sub(r"//[^\n]*", "", head)
    head = "\n".join(line for line in head.splitlines() if not line.strip().startswith("#"))
    # 抹掉数组初始化用的花括号，避免把 `= {0.0}` 误判成代码块。
    head = re.sub(r"\{[^{}]*\}", "", head, flags=re.S)

    names: set[str] = set()
    for statement in head.split(";"):
        declaration = _DECL_TYPE_RE.match(statement.strip())
        if declaration is None:
            continue
        for declarator in _split_top_level(declaration.group(1), ","):
            name_match = re.match(r"\s*(?:[*&]\s*)*([A-Za-z_]\w*)", declarator)
            if name_match:
                names.add(name_match.group(1))
    return ModuleSignature(name=cpp_path.parent.name, variables=frozenset(names), source=cpp_path)


def load_signatures(source_root: Path) -> dict[str, ModuleSignature]:
    """读取所有“目录名与 .cpp 同名”的模块根源码。"""

    module_root = source_root / "AlgModule"
    if not module_root.is_dir():
        raise SystemExit(f"模块目录不存在：{module_root}")

    signatures: dict[str, ModuleSignature] = {}
    for directory in sorted(module_root.iterdir(), key=lambda path: path.name):
        cpp_path = directory / f"{directory.name}.cpp"
        if directory.is_dir() and cpp_path.is_file():
            signatures[directory.name] = parse_module_signature(cpp_path)
    if not signatures:
        raise SystemExit(f"在 {module_root} 下没有找到 <模块>/<模块>.cpp")
    return signatures


def load_project_db(source_root: Path, project: str) -> tuple[dict[str, Any], Path]:
    path = source_root / "AlgProject" / project / f"{project}_DB.PJTDB"
    if not path.is_file():
        raise SystemExit(f"工程数据库不存在：{path}")
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise SystemExit(f"工程数据库顶层不是 JSON 对象：{path}")
    return data, path


def iter_mods(db: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    """按数字序号稳定遍历 MOD* 对象。"""

    keys = [key for key in db if re.fullmatch(r"MOD\d+", key)]
    for key in sorted(keys, key=lambda item: int(item[3:])):
        value = db[key]
        if isinstance(value, dict):
            yield key, value


def match_module(variable_keys: set[str], signatures: dict[str, ModuleSignature]) -> Match:
    """用 Jaccard 主分与覆盖率次分做 best-match。

    同分时按模块名排序取第一个，并把所有并列候选记录在 ``ties`` 中。倍思鹿的
    PJTDB 不保存模块名，因此并列签名（如蒸发器/蒸发式冷凝器）无法只靠键集合区分。
    """

    ranked: list[tuple[float, float, str, frozenset[str], frozenset[str]]] = []
    for name, signature in signatures.items():
        signature_vars = signature.variables
        intersection = variable_keys & signature_vars
        union = variable_keys | signature_vars
        score = len(intersection) / len(union) if union else 0.0
        coverage = len(intersection) / len(signature_vars) if signature_vars else 0.0
        ranked.append(
            (
                score,
                coverage,
                name,
                frozenset(signature_vars - variable_keys),
                frozenset(variable_keys - signature_vars),
            )
        )
    if not ranked:
        raise ValueError("没有可用于匹配的模块签名")

    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    best = ranked[0]
    ties = tuple(
        item[2] for item in ranked if abs(item[0] - best[0]) < 1e-12 and abs(item[1] - best[1]) < 1e-12
    )
    return Match(
        module=best[2],
        score=best[0],
        coverage=best[1],
        missing=tuple(sorted(best[3])),
        extra=tuple(sorted(best[4])),
        ties=ties,
        key_count=len(variable_keys),
    )


def normalize_value(value: Any) -> Any:
    """保留原始结构，并把 ``AryDoubleN`` / ``AryIntN`` 包装展开成列表。

    PJTDB 的数组分量形如 ``{"AryDouble0": [...], ...}``；这里按编号排序展开为
    ``[[...], [...]]``，其余 dict/list 递归处理。标量保持不变。
    """

    if isinstance(value, dict):
        if value and all(_ARRAY_WRAPPER_RE.fullmatch(str(key)) for key in value):
            return [normalize_value(value[key]) for key in sorted(value, key=lambda item: int(re.sub(r"\D", "", item)))]
        return {str(key): normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    return value


def _flatten_numbers(value: Any) -> list[float]:
    """收集变量值中的数值，用于判断快照是否全零。"""

    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, list):
        numbers: list[float] = []
        for item in value:
            numbers.extend(_flatten_numbers(item))
        return numbers
    if isinstance(value, dict):
        numbers = []
        for item in value.values():
            numbers.extend(_flatten_numbers(item))
        return numbers
    return []


def is_computed_key(key: str) -> bool:
    if key in _COMPUTED_NAMES or key in _STATE_NAMES:
        return True
    return key.endswith(_COMPUTED_SUFFIXES)


def build_variables(mod: dict[str, Any]) -> dict[str, Any]:
    return {key: normalize_value(mod[key]) for key in sorted(mod)}


def build_expected_snapshot(variables: dict[str, Any], match: Match) -> dict[str, Any]:
    computed = sorted(key for key in variables if is_computed_key(key))
    inputs = sorted(key for key in variables if key not in computed)
    computed_values = {key: _flatten_numbers(variables[key]) for key in computed}
    all_zero = bool(computed) and all(
        all(abs(number) < 1e-30 for number in numbers) for numbers in computed_values.values() if numbers
    )
    note = (
        "computed_keys 只是按变量名做的启发式标注，表示倍思鹿模块通常会回写这些量；"
        "本快照未运行倍思鹿，无法保证它们来自收敛后的迭代。"
    )
    if all_zero:
        note += " 本算例中这些计算量全为 0，尤其不能当作收敛结果。"
    if match.missing:
        note += f" 模块签名中另有 {len(match.missing)} 个变量未出现在 PJTDB：{', '.join(match.missing)}。"
    return {
        "kind": "saved_state_snapshot",
        "convergence_verified": False,
        "convergence_note": "不能保证是收敛后结果；仅代表 PJTDB 当前保存槽位。",
        "computed_keys": computed,
        "input_or_boundary_keys": inputs,
        "computed_values_all_zero": all_zero,
        "note": note,
    }


def build_notes(mod: dict[str, Any], match: Match, variables: dict[str, Any]) -> str:
    notes = [
        f"{match.key_count} 个变量键与《{match.module}》根 .cpp 的全局声明匹配，"
        f"Jaccard={match.score:.4f}，签名覆盖率={match.coverage:.4f}。"
    ]
    if match.missing:
        notes.append(
            f"签名比快照多 {len(match.missing)} 个变量（{', '.join(match.missing)}），"
            "说明该键未写入 PJTDB，或只在运行时生成。"
        )
    if match.extra:
        notes.append(f"快照比签名多 {len(match.extra)} 个变量（{', '.join(match.extra)}），可能来自运行时扩展。")
    if len(match.ties) > 1:
        notes.append(
            f"同签名候选：{'、'.join(match.ties)}；module_guess 仅按名称稳定排序取首个，不是唯一真值。"
        )
    if any(key in variables for key in ("X",)) or any(key.endswith("_X") for key in variables):
        notes.append("AryDoubleN/AryIntN 包装已展开为列表的列表，其余字段保持 PJTDB 原结构。")
    if int(mod.get("S_T", [0])[0] if isinstance(mod.get("S_T"), list) and mod.get("S_T") else 0) == 0:
        notes.append("S_T[0]=0，该对象在保存时可能未启用或未参与计算。")
    return " ".join(notes)


def build_usage(spec: CaseSpec) -> dict[str, str]:
    return {
        "as_boundary": (
            f"把 IM*/EX* 端口数组按索引映射为 FluidNet 边界或节点初值，用于复现《{spec.module}》"
            "所在支路的入口/出口条件；工质与单位必须先按 DATA_CONTRACT 换算。"
        ),
        "as_initial_state": (
            "把非零状态量（如罐体液位、换热器金属焓、电路 U/i）作为同拓扑试算的初值，"
            "只用于缩短迭代路径，不要求逐点复现。"
        ),
        "as_regression_target": (
            "仅比较变量集合、量级和趋势（例如压降方向、流量范围），不设精度阈值，"
            "不声称与倍思鹿数值等价。"
        ),
        "not_for": "不得作为数值验收基准、性能基准，也不能证明两相/可压缩等模型能力。",
    }


def build_case_payload(
    *,
    case_id: str,
    project: str,
    source_db: Path,
    source_root: Path,
    object_key: str,
    mod: dict[str, Any],
    match: Match,
    spec: CaseSpec,
) -> dict[str, Any]:
    variables = build_variables(mod)
    return {
        "case_id": case_id,
        "source_db": source_db.relative_to(source_root).as_posix(),
        "project": project,
        "object_key": object_key,
        "module_guess": match.module,
        "match_score": round(match.score, 4),
        "variables": variables,
        "notes": build_notes(mod, match, variables),
        "provenance": PROVENANCE,
        "expected_snapshot": build_expected_snapshot(variables, match),
        "usage": build_usage(spec),
    }


def select_cases(
    databases: dict[str, dict[str, Any]],
    matches: dict[tuple[str, str], Match],
) -> list[tuple[CaseSpec, str, dict[str, Any], Match]]:
    """按 CASE_PLAN 选择每个设备族的首个未占用 MOD。"""

    selected: list[tuple[CaseSpec, str, dict[str, Any], Match]] = []
    used: set[tuple[str, str]] = set()
    for spec in CASE_PLAN:
        db = databases[spec.project]
        chosen: tuple[str, dict[str, Any], Match] | None = None
        for object_key, mod in iter_mods(db):
            match = matches[(spec.project, object_key)]
            if (spec.project, object_key) in used:
                continue
            if match.module == spec.module and match.score >= 0.9:
                chosen = (object_key, mod, match)
                break
        if chosen is None:
            raise SystemExit(f"未找到 {spec.project} 中匹配《{spec.module}》的 MOD")
        used.add((spec.project, chosen[0]))
        selected.append((spec, chosen[0], chosen[1], chosen[2]))
    return selected


def case_id_for(project: str, object_key: str, family: str) -> str:
    return f"baselu-{project.lower()}-{object_key.lower()}-{family}"


def write_cases(
    selected: list[tuple[CaseSpec, str, dict[str, Any], Match]],
    db_paths: dict[str, Path],
    source_root: Path,
    out_dir: Path,
) -> list[dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[dict[str, Any]] = []
    for spec, object_key, mod, match in selected:
        case_id = case_id_for(spec.project, object_key, spec.family)
        payload = build_case_payload(
            case_id=case_id,
            project=spec.project,
            source_db=db_paths[spec.project],
            source_root=source_root,
            object_key=object_key,
            mod=mod,
            match=match,
            spec=spec,
        )
        path = out_dir / f"{case_id}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        written.append(payload)
    return written


def print_summary(cases: list[dict[str, Any]], out_dir: Path) -> None:
    header = "case_id\tmodule\tscore\tkeys"
    print(header)
    print("-" * 60)
    for case in cases:
        print(
            f"{case['case_id']}\t{case['module_guess']}\t"
            f"{case['match_score']:.3f}\t{len(case['variables'])}"
        )
    perfect = sum(1 for case in cases if case["match_score"] >= 0.9999)
    print("-" * 60)
    print(f"共 {len(cases)} 个算例；精确键集匹配 {perfect} 个；输出目录 {out_dir}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="提取倍思鹿参考算例快照（只读 PJTDB 与模块源码）")
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="倍思鹿安装/资料包根目录（含 AlgProject 与 AlgModule），默认取仓库相邻目录",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="fixture 输出目录，默认 tests/fixtures/baselu",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    source_root = args.source.resolve()
    out_dir = args.out.resolve()

    signatures = load_signatures(source_root)
    databases: dict[str, dict[str, Any]] = {}
    db_paths: dict[str, Path] = {}
    matches: dict[tuple[str, str], Match] = {}
    for project in PROJECT_ORDER:
        db, db_path = load_project_db(source_root, project)
        databases[project] = db
        db_paths[project] = db_path
        for object_key, mod in iter_mods(db):
            matches[(project, object_key)] = match_module(set(mod), signatures)

    selected = select_cases(databases, matches)
    cases = write_cases(selected, db_paths, source_root, out_dir)
    print_summary(cases, out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
