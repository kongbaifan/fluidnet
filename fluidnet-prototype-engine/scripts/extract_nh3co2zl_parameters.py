#!/usr/bin/env python3
"""从倍思鹿 NH3CO2ZL 工程数据库提取对象参数快照（M2-C 第二部分）。

只读 ``AlgProject/NH3CO2ZL/NH3CO2ZL_DB.PJTDB`` 与 ``AlgModule/<module>/<module>.cpp``：
PJTDB 给出每个 ``MOD*`` 对象的变量名与数值，模块根 .cpp 给出``void runing()`` 之前的
全局变量签名，两者做 Jaccard 匹配得到 ``module_guess``。

脚本不 import ``extract_baselu_cases``（独立实现，便于两个提取器各自演进），
不运行倍思鹿程序，也不解析加密的 ``.pjt`` / ``.Modu``：PJTDB 里没有连接字段，
因此本快照只描述对象参数，不描述拓扑（``topology_available`` 恒为 false）。

输出是确定性 JSON：同一份 PJTDB + 同一批 .cpp 连续运行两次，字节完全一致。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

PROJECT = "NH3CO2ZL"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = PROJECT_ROOT / "tests" / "fixtures" / "nh3co2zl" / "parameters.json"
SOURCE_DIR_NAME = "倍思鹿数值仿真-V5.3"
SOURCE_ENV = "FLUIDNET_BEISILU_SOURCE"

# 报告与文档必须能直接引用这些类别的计数，即使某个类别在本工程里是 0 个对象。
REQUIRED_CATEGORIES = ("压缩机", "蒸发式冷凝器", "热力膨胀阀", "罐体卧式", "罐体立式", "冷库库房")

PROVENANCE = (
    "PJTDB 保存槽位快照；未运行倍思鹿；.pjt/.Modu 为加密二进制，未解析；"
    "module_guess 由变量键集合与模块根 .cpp 全局变量签名的 Jaccard 匹配得到，不是官方对象分类。"
)

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


def _candidate_roots() -> Iterator[Path]:
    """按确定顺序给出可能的倍思鹿资料包根目录，不写死盘符。"""

    override = os.environ.get(SOURCE_ENV)
    if override:
        yield Path(override).expanduser()
    bases = [Path.cwd(), *PROJECT_ROOT.parents]
    seen: set[Path] = set()
    for base in bases:
        try:
            resolved = base.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        yield resolved / SOURCE_DIR_NAME
        if base.is_dir():
            for child in sorted(base.iterdir(), key=lambda path: path.name):
                if child.is_dir() and child.name.startswith("倍思鹿数值仿真"):
                    yield child


def resolve_source(explicit: Path | None) -> Path:
    """定位含 ``AlgProject/<PROJECT>`` 的资料包根目录。"""

    if explicit is not None:
        candidate = explicit.expanduser().resolve()
        if (candidate / "AlgProject" / PROJECT).is_dir():
            return candidate
        raise SystemExit(f"--source 下没有 AlgProject/{PROJECT}：{candidate}")

    for candidate in _candidate_roots():
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if (resolved / "AlgProject" / PROJECT).is_dir():
            return resolved
    raise SystemExit(
        f"找不到倍思鹿资料包：请用 --source 指定含 AlgProject 与 AlgModule 的目录（也可设置环境变量 {SOURCE_ENV}）。"
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
    """解析 ``void runing()`` 之前的全局变量名（支持数组与逗号多声明）。"""

    text = cpp_path.read_text(encoding="utf-8-sig", errors="replace")
    match = _RUNING_RE.search(text)
    head = text[: match.start()] if match else text
    head = _strip_function_bodies(head)
    head = re.sub(r"/\*.*?\*/", "", head, flags=re.S)
    head = re.sub(r"//[^\n]*", "", head)
    head = "\n".join(line for line in head.splitlines() if not line.strip().startswith("#"))
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


def load_project_db(source_root: Path) -> tuple[dict[str, Any], Path]:
    """读取 ``AlgProject/NH3CO2ZL/NH3CO2ZL_DB.PJTDB``（明文 JSON）。"""

    path = source_root / "AlgProject" / PROJECT / f"{PROJECT}_DB.PJTDB"
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


def best_match(keys: set[str], signatures: dict[str, ModuleSignature]) -> tuple[str, float, float, tuple[str, ...]]:
    """Jaccard 主分 + 签名覆盖率次分；并列时按模块名排序，并保留全部并列候选。"""

    ranked: list[tuple[float, float, str]] = []
    for name, signature in signatures.items():
        signature_vars = signature.variables
        intersection = keys & signature_vars
        union = keys | signature_vars
        score = len(intersection) / len(union) if union else 0.0
        coverage = len(intersection) / len(signature_vars) if signature_vars else 0.0
        ranked.append((score, coverage, name))
    if not ranked:
        raise ValueError("没有可用于匹配的模块签名")

    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    best_score, best_coverage = ranked[0][0], ranked[0][1]
    ties = tuple(
        name
        for score, coverage, name in ranked
        if abs(score - best_score) < 1e-12 and abs(coverage - best_coverage) < 1e-12
    )
    return ranked[0][2], best_score, best_coverage, ties


def normalize_value(value: Any) -> Any:
    """把 ``AryDoubleN`` / ``AryIntN`` 包装按编号展开为列表，其余结构递归保留。"""

    if isinstance(value, dict):
        if value and all(_ARRAY_WRAPPER_RE.fullmatch(str(key)) for key in value):
            ordered = sorted(value, key=lambda item: int(re.sub(r"\D", "", item)))
            return [normalize_value(value[key]) for key in ordered]
        return {str(key): normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    return value


def build_variables(mod: dict[str, Any]) -> dict[str, Any]:
    return {key: normalize_value(mod[key]) for key in sorted(mod)}


def build_summary(objects: list[dict[str, Any]]) -> dict[str, int]:
    """按 module_guess 计数，并显式补 0 以便文档直接引用。"""

    counts: dict[str, int] = {}
    for obj in objects:
        name = obj["module_guess"]
        counts[name] = counts.get(name, 0) + 1
    for name in REQUIRED_CATEGORIES:
        counts.setdefault(name, 0)
    return {name: counts[name] for name in sorted(counts, key=lambda item: (-counts[item], item))}


def find_anomalies(objects: list[dict[str, Any]]) -> list[str]:
    """挑出物理量明显越界的对象，提醒使用方先做量纲/合理性筛查。"""

    anomalies: list[str] = []
    for obj in objects:
        variables = obj["variables"]
        for key, low, high in (("IM0_TEMP", -100.0, 200.0), ("EX0_TEMP", -100.0, 200.0)):
            value = variables.get(key)
            if isinstance(value, list) and value and isinstance(value[0], (int, float)):
                number = float(value[0])
                if not low <= number <= high:
                    anomalies.append(f"{obj['key']}.{key}[0]={number:.2f}")
                    break
    return anomalies


def build_caveats(ties_by_module: dict[tuple[str, ...], list[str]], anomalies: list[str]) -> list[str]:
    caveats = [
        "PJTDB 只含 NOD*/MOD*/PjtVarValue 三类键，全部取值均为数值，没有字符串、端口、连接或相邻对象字段，"
        "因此无法从中恢复管路拓扑；.pjt 与 .Modu 是加密二进制（非 JSON），未解密、未运行程序。",
        "module_guess 只是“变量键集合 ↔ 模块根 .cpp 全局变量签名”的 Jaccard best-match，"
        "同签名模块无法区分，也不等于倍思鹿官方的对象分类。",
        "NOD 与 MOD 之间没有引用字段：63 个节点只保存集总端口变量，不能据此把模块分配到节点。",
        "快照是 PJTDB 当前保存槽位，未验证是否收敛，也不代表额定工况；"
        "部分计算量存在 -998/998 之类的哨兵值，需按倍思鹿约定清洗。",
        "AryDoubleN/AryIntN 已按编号展开为列表；其余字段保持 PJTDB 原结构，未做单位换算。",
    ]
    for modules, keys in ties_by_module.items():
        caveats.append(
            f"同签名候选『{'、'.join(modules)}』无法由键集合区分；对象 {', '.join(keys)} 归入其中的"
            f"『{modules[0]}』，其余候选需人工指认。"
        )
    if anomalies:
        caveats.append(
            f"以下对象存在明显越界的第一温度值（°C），使用前必须量纲/合理性筛查：{', '.join(anomalies[:8])}"
            + ("…" if len(anomalies) > 8 else "")
        )
    return caveats


def build_payload(
    source_root: Path,
    db_path: Path,
    objects: list[dict[str, Any]],
    ties_by_module: dict[tuple[str, ...], list[str]],
) -> dict[str, Any]:
    return {
        "project": PROJECT,
        "source": db_path.relative_to(source_root).as_posix(),
        "objects": objects,
        "summary": build_summary(objects),
        "topology_available": False,
        "provenance": PROVENANCE,
        "caveats": build_caveats(ties_by_module, find_anomalies(objects)),
    }


def count_nodes(db: dict[str, Any]) -> int:
    return sum(1 for key in db if re.fullmatch(r"NOD\d+", key))


def print_summary(payload: dict[str, Any], out_path: Path, size: int, node_count: int) -> None:
    objects = payload["objects"]
    print(
        f"工程 {payload['project']}：{node_count} 个 NOD / {len(objects)} 个 MOD；拓扑字段 0（topology_available=false）"
    )
    print("-" * 96)
    print("module_guess\t对象数\t示例对象（前 6 个）")
    for name, count in payload["summary"].items():
        sample = [obj["key"] for obj in objects if obj["module_guess"] == name][:6]
        print(f"{name}\t{count}\t{', '.join(sample) if sample else '—'}")
    print("-" * 96)
    exact = sum(1 for obj in objects if obj["score"] >= 0.9999)
    print(f"共 {len(objects)} 个对象；精确键集匹配 {exact} 个；输出 {out_path}（{size} 字节）")
    for caveat in payload["caveats"]:
        if caveat.startswith("同签名候选") or caveat.startswith("以下对象"):
            print(f"注意：{caveat}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="提取倍思鹿 NH3CO2ZL 工程的对象参数快照（只读 PJTDB 与模块源码）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help=f"倍思鹿资料包根目录（含 AlgProject 与 AlgModule）；缺省自动查找，可用 {SOURCE_ENV} 覆盖",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="fixture 输出文件",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    source_root = resolve_source(args.source)
    out_path = args.out.expanduser().resolve()
    # --out 既接受文件路径，也接受目录：目录时写入 parameters.json。
    if out_path.suffix.lower() != ".json":
        out_path = out_path / "parameters.json"

    signatures = load_signatures(source_root)
    db, db_path = load_project_db(source_root)

    objects: list[dict[str, Any]] = []
    ties_by_module: dict[tuple[str, ...], list[str]] = {}
    for object_key, mod in iter_mods(db):
        module, score, _coverage, ties = best_match(set(mod), signatures)
        if len(ties) > 1:
            ties_by_module.setdefault(ties, []).append(object_key)
        objects.append(
            {
                "key": object_key,
                "module_guess": module,
                "score": round(score, 4),
                "variables": build_variables(mod),
            }
        )
    if not objects:
        raise SystemExit(f"{db_path} 里没有 MOD* 对象")

    payload = build_payload(source_root, db_path, objects, ties_by_module)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n"：避免 Windows 把 \n 改写成 \r\n，保证跨平台 SHA256 一致。
    out_path.write_text(text, encoding="utf-8", newline="\n")

    print_summary(payload, out_path, len(text.encode("utf-8")), count_nodes(db))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
