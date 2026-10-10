"""Render the review's three architecture diagrams as PNG and editable SVG."""
from __future__ import annotations

import math
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".cache/report-runtime"))
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[1] / "assets"
REGULAR = Path("C:/Windows/Fonts/msyh.ttc")
BOLD = Path("C:/Windows/Fonts/msyhbd.ttc")
NAVY, BLUE, TEAL, GRAY = "#163047", "#2966a3", "#087f8c", "#536777"


class Diagram:
    def __init__(self, width, height, title, subtitle):
        self.width, self.height = width, height
        self.image = Image.new("RGB", (width, height), "#ffffff")
        self.draw = ImageDraw.Draw(self.image)
        self.svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">', '<rect width="100%" height="100%" fill="white"/>']
        self.text(55, 45, title, 42, NAVY, bold=True)
        self.text(58, 112, subtitle, 25, GRAY)

    def font(self, size, bold=False):
        return ImageFont.truetype(str(BOLD if bold and BOLD.exists() else REGULAR), size)

    def text(self, x, y, value, size=27, color=NAVY, bold=False, center=False):
        font = self.font(size, bold)
        width = self.draw.textlength(value, font=font)
        if center:
            x -= width / 2
        assert x >= 0 and x + width <= self.width, (value, x, width)
        assert 0 <= y <= self.height - size, (value, y)
        self.draw.text((x, y), value, font=font, fill=color, anchor="lt")
        self.svg.append(f'<text x="{x:.1f}" y="{y + size:.1f}" font-family="Microsoft YaHei, sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}">{escape(value)}</text>')

    def rect(self, x, y, width, height, fill, border="#bfd0df", radius=18):
        self.draw.rounded_rectangle((x, y, x + width, y + height), radius=radius, fill=fill, outline=border, width=2)
        self.svg.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" fill="{fill}" stroke="{border}" stroke-width="2"/>')

    def wrap(self, text, size, width):
        parts, current = [], ""
        for char in text:
            if current and self.draw.textlength(current + char, font=self.font(size)) > width:
                parts.append(current)
                current = ""
            current += char
        if current:
            parts.append(current)
        return parts

    def box(self, x, y, width, height, title, lines=(), fill="#f4f8fc", border="#a9c5dc", color=NAVY):
        self.rect(x, y, width, height, fill, border)
        title_size = 29
        while self.draw.textlength(title, font=self.font(title_size, True)) > width - 28:
            title_size -= 1
        body_size = 25
        while True:
            body = [part for line in lines for part in self.wrap(line, body_size, width - 32)]
            total = title_size + (18 if body else 0) + len(body) * (body_size + 10)
            if total <= height - 28 or body_size <= 20:
                break
            body_size -= 1
        assert total <= height - 20, (title, total, height)
        top = y + (height - total) / 2
        self.text(x + width / 2, top, title, title_size, color, True, True)
        top += title_size + 18
        for line in body:
            self.text(x + width / 2, top, line, body_size, GRAY, center=True)
            top += body_size + 10

    def line(self, points, color=BLUE, width=4, dashed=False, end=True, start=False):
        if not dashed:
            self.draw.line(points, fill=color, width=width, joint="curve")
        else:
            for a, b in zip(points, points[1:]):
                length = math.dist(a, b)
                for step in range(0, int(length), 18):
                    t1, t2 = step / length, min(step + 10, length) / length
                    self.draw.line([(a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1), (a[0] + (b[0] - a[0]) * t2, a[1] + (b[1] - a[1]) * t2)], fill=color, width=width)
        coords = " ".join(f"{x},{y}" for x, y in points)
        dash = ' stroke-dasharray="10 8"' if dashed else ""
        self.svg.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round"{dash}/>')
        if end:
            self.head(points[-2], points[-1], color)
        if start:
            self.head(points[1], points[0], color)

    def head(self, source, tip, color):
        angle = math.atan2(tip[1] - source[1], tip[0] - source[0])
        points = [tip, (tip[0] - 15 * math.cos(angle) + 7 * math.sin(angle), tip[1] - 15 * math.sin(angle) - 7 * math.cos(angle)), (tip[0] - 15 * math.cos(angle) - 7 * math.sin(angle), tip[1] - 15 * math.sin(angle) + 7 * math.cos(angle))]
        self.draw.polygon(points, fill=color)
        self.svg.append(f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x,y in points)}" fill="{color}"/>')

    def save(self, name):
        OUT.mkdir(parents=True, exist_ok=True)
        self.image.save(OUT / f"{name}.png", optimize=True)
        (OUT / f"{name}.svg").write_text("\n".join(self.svg + ["</svg>"]), encoding="utf-8")
        print(name, self.image.size)


def reference():
    d = Diagram(1600, 1080, "参考资料：模块阶段与网络阶段", "资料描述  |  PDF 第 3-7 页；示意图不推定 NET 内部数值算法")
    d.box(60, 250, 340, 210, "主控程序", ["加载项目拓扑", "协调模块阶段", "检查 NetCk 就绪标记"])
    for x, title in [(520, "管道类模块"), (850, "阀门类模块"), (1180, "其他设备模块")]:
        d.box(x, 250, 280, 170, title, ["计算本轮设备关系", "提交并网信息"], fill="#eef9f8", border="#9bcfc9")
    d.line([(400, 325), (460, 325), (460, 205), (1320, 205)], end=False)
    for x in (660, 990, 1320):
        d.line([(x, 205), (x, 250)])
    d.text(985, 164, "同一模块阶段并行", 26, BLUE, center=True)
    for x in (660, 990, 1320):
        d.line([(x, 420), (x, 485)], end=False)
    d.line([(660, 485), (1320, 485)], end=False)
    d.line([(990, 485), (990, 570)])
    d.text(1210, 523, "就绪后，由主控调用", 25, BLUE, center=True)
    d.box(790, 570, 400, 165, "NET 网络引擎", ["统一解算网络压力与流量", "维护拓扑与模块映射"], fill="#edf5ff")
    d.line([(790, 650), (230, 650), (230, 460)])
    d.text(490, 605, "完成后进入下一轮模块计算", 25, BLUE, center=True)
    d.box(60, 850, 340, 155, "界面 / 外部程序", ["读取结果、写入参数"], fill="#fbf7ee", border="#d9c79d")
    d.box(520, 850, 940, 155, "运行数据存储 DLL", ["拓扑、设备外置变量及主控指令；内部共享机制待 SDK 确认"], fill="#fbf7ee", border="#d9c79d")
    d.line([(400, 925), (520, 925)], TEAL, dashed=True, start=True)
    d.line([(990, 735), (990, 850)], TEAL, dashed=True, start=True)
    d.text(810, 785, "状态与变量交换", 24, TEAL, center=True)
    d.line([(1460, 365), (1520, 365), (1520, 805), (1320, 805), (1320, 850)], TEAL, dashed=True, start=True)
    d.text(1375, 615, "各模块", 24, TEAL, center=True)
    d.text(1375, 651, "均读写", 24, TEAL, center=True)
    d.text(58, 1030, "实线：阶段顺序  ·  虚线：数据交换  ·  多个模块不等同于已证明网络矩阵并行", 23, GRAY)
    d.save("reference-architecture")


def current():
    d = Diagram(1680, 1190, "当前实现：任务并行，任务内统一求解", "当前源码  |  HTTP 服务与计算进程分离；设备数值行为分布在现有内核中")
    d.rect(35, 205, 405, 865, "#f6f8fb")
    d.rect(490, 205, 1135, 865, "#fafcfe")
    d.text(235, 225, "服务进程", 28, BLUE, True, True)
    d.text(1055, 225, "计算工作进程（每个运行任务一个）", 28, BLUE, True, True)
    d.box(70, 300, 335, 130, "Web / API", ["项目编辑、运行与查询"])
    d.box(70, 520, 335, 180, "JobManager", ["请求、命令与最新状态", "默认最多 2 个 spawn 进程", "计算进程 daemon=True"])
    d.box(70, 890, 335, 140, "Store / 文件查询", ["SQLite 元数据", "历史曲线与事件"])
    d.line([(235, 430), (235, 520)], start=True)
    d.box(555, 310, 415, 135, "项目编译", ["Project → compile_project", "节点、支路与介质归属"])
    d.box(1100, 310, 440, 135, "SimulationSession", ["控制时钟、试算与接受状态"])
    d.line([(405, 585), (460, 585), (460, 377), (555, 377)])
    d.line([(970, 377), (1100, 377)])
    d.box(575, 580, 400, 200, "solve_network", ["水力 Newton 与活动集", "热力焓平衡", "水热外迭代"])
    d.line([(762, 445), (762, 580)])
    d.text(635, 500, "稳态 / 动态共用", 25, BLUE, center=True)
    d.line([(1320, 445), (1320, 490), (960, 490), (960, 580)])
    d.text(1115, 457, "时间推进", 24, BLUE, center=True)
    d.box(1120, 560, 420, 120, "MediumRegistry / IF97", ["物性缓存与适用域检查"], fill="#eef9f8", border="#9bcfc9")
    d.line([(975, 620), (1120, 620)], TEAL, start=True)
    d.box(1120, 765, 420, 120, "snapshot", ["压力、流量、温度与诊断"])
    d.line([(975, 730), (1040, 730), (1040, 825), (1120, 825)])
    d.line([(1120, 855), (465, 855), (465, 660), (405, 660)])
    d.text(775, 817, "最新帧与回执共用可丢弃通道", 24, BLUE, center=True)
    d.box(1120, 950, 420, 100, "Recorder", ["同进程压缩并刷盘"], fill="#fbf7ee", border="#d9c79d")
    d.line([(1330, 885), (1330, 950)])
    d.box(555, 950, 420, 100, "运行文件", ["曲线、事件、result.json"], fill="#fbf7ee", border="#d9c79d")
    d.line([(1120, 1000), (975, 1000)], TEAL)
    d.line([(555, 1000), (405, 1000)], TEAL)
    d.text(58, 1110, "F01：容差配置未接入  ·  F07：暂停尾部不可见  ·  F08：回执缺 ID 且可丢弃", 25, GRAY)
    d.text(58, 1150, "仅绘制主要职责与数据流；组合外壳不会创建独立的网络求解分区。", 23, GRAY)
    d.save("current-architecture")


def target():
    d = Diagram(1680, 1285, "建议目标：试算与接受状态分离", "建议未实施  |  渐进适配现有求解器；先明确状态、数值与设备协议，再按测量并行")
    d.box(70, 220, 400, 135, "项目定义", ["拓扑、参数、型号与单位"])
    d.box(610, 220, 450, 135, "计算图", ["方程索引、依赖与原图映射"])
    d.box(1190, 220, 420, 135, "设备模型协议", ["能力、状态、方程与观测"])
    d.line([(470, 287), (610, 287)])
    d.line([(1060, 287), (1190, 287)])
    d.box(70, 490, 400, 170, "已接受状态 S_n", ["物理状态与控制状态", "本步有效命令与事件"], fill="#eef9f8", border="#9bcfc9")
    d.box(610, 490, 450, 170, "设备方程贡献", ["只读试算、按需批量或并行", "残差、导数与事件"])
    d.box(1190, 490, 420, 170, "求解与时间协调", ["网络装配与耦合迭代", "物理域、误差与事件检查"])
    d.line([(835, 355), (835, 490)])
    d.line([(1400, 355), (1400, 415), (915, 415), (915, 490)])
    d.line([(470, 575), (610, 575)])
    d.text(540, 533, "只读", 23, BLUE, center=True)
    d.line([(1060, 575), (1190, 575)])
    d.box(1190, 805, 420, 155, "统一提交 S_n+1", ["按契约更新全部接受状态", "生成有序观测与回执"], fill="#eef9f8", border="#9bcfc9")
    d.line([(1460, 660), (1460, 805)], TEAL)
    d.text(1535, 719, "接受", 24, TEAL, center=True)
    d.line([(1300, 660), (1300, 722), (835, 722), (835, 660)], BLUE)
    d.text(1020, 755, "未接受：重试或缩步", 25, BLUE, center=True)
    d.line([(1190, 882), (270, 882), (270, 660)], TEAL)
    d.text(690, 836, "下一步读取统一的已接受状态", 25, TEAL, center=True)
    d.line([(1400, 960), (1400, 1005)], end=False)
    d.line([(245, 1005), (1415, 1005)], end=False)
    items = [(70, "可靠命令回执", "按 ID 查询与补读"), (460, "最新观测", "允许合并展示帧"), (850, "历史记录", "采样、背压与落盘水位"), (1240, "检查点（按需）", "完整续算状态与版本")]
    for x, title, body in items:
        d.line([(x + 175, 1005), (x + 175, 1060)])
        d.box(x, 1060, 350, 140, title, [body], fill="#fbf7ee", border="#d9c79d")
    d.text(58, 1230, "失败与命令拒绝也进入可靠通道；分别约定采样与持久化，不要求立即拆成多个进程。", 24, GRAY)
    d.save("target-architecture")


if __name__ == "__main__":
    reference()
    current()
    target()
