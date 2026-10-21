"""Read full style cards from the authoritative Markdown; never write project state."""
import argparse
from decimal import Decimal
import math
from pathlib import Path
import re
import sys

STYLE_DIR = Path(__file__).resolve().parents[1] / 'references' / 'style-bible'


def _section(text, predicate):
    sections = re.split(r'(?m)(?=^## )', text)
    matches = [s.strip() for s in sections if predicate(s.splitlines()[0])]
    if len(matches) != 1:
        raise ValueError('未找到唯一完整卡；请按参数库补录模板人工组装，不生成伪造参数')
    return matches[0]


def load_card(style_id):
    pattern = rf'编号\s*0?{style_id}(?!\d)'
    card = _section((STYLE_DIR / 'director-param-library.md').read_text(encoding='utf-8'),
                    lambda h: bool(re.search(pattern, h)))
    block = _section((STYLE_DIR / 'style-prefix-blocks.md').read_text(encoding='utf-8'),
                     lambda h: bool(re.search(pattern, h)) or
                     (style_id == 9 and h == '## 徐克块') or
                     (style_id == 10 and h == '## 王家卫块'))
    rows = re.findall(r'^\| (\d+) \|', card, re.M)
    if rows != [str(i) for i in range(1, 12)]:
        raise ValueError('完整卡槽位必须为 1 至 11，且不得重号')
    blocks = re.findall(r'```text\n(.*?)\n```', block, re.S)
    if len(blocks) != 2:
        raise ValueError('成品块必须包含 STYLE 和 PERFORMANCE 两段')
    return card, block, '\n\n'.join(blocks)


def _range(values, unit):
    if not values or any(not math.isfinite(v) or v <= 0 for v in values) or values[0] > values[1]:
        raise ValueError('请提供项目已确认的正数区间 MIN MAX，且 MIN <= MAX')
    if unit == 'mm' and any(v != int(v) for v in values):
        raise ValueError('现有 C23 焦距区间只支持整数 mm，请使用项目确认的整数区间')
    return '[' + ', '.join(('1:' + (str(int(v)) if v == int(v) else format(Decimal(str(v)), 'f'))) if unit == 'ratio' else f'{int(v)}mm'
                            for v in values) + ']'


def render_selection(style_id, output='card', light=None, lens=None):
    card, block, prompt = load_card(style_id)
    if output == 'card':
        if light is not None or lens is not None:
            raise ValueError('区间参数仅用于 --format prompt，避免误以为已经应用')
        return card + '\n\n' + block
    if style_id == 36:
        if light is None or lens is None:
            raise ValueError('诺兰投喂块需要项目已确认的 --light-range 和 --lens-range；未知值不自动补造')
        prompt = prompt.replace('{{LIGHT_RANGE}}', _range(light, 'ratio'))
        prompt = prompt.replace('{{LENS_RANGE}}', _range(lens, 'mm'))
    elif light is not None or lens is not None:
        raise ValueError('区间覆盖仅适用于编号 36；其他卡保持既有正文')
    return prompt


def run_selection_cli(styles, render_recommendation):
    """No arguments preserves the original demos and all recommendation APIs."""
    if len(sys.argv) == 1:
        return False
    parser = argparse.ArgumentParser(description='按题材推荐，或在明确选卡后读取完整参数与成品块')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--select', type=int, help='明确选择已有风格编号；不会自动确认项目锁')
    group.add_argument('--genre', help='题材推荐，保留原排序及排除规则')
    parser.add_argument('--format', choices=('card', 'prompt'), default='card')
    parser.add_argument('--light-range', nargs=2, type=float, metavar=('MIN', 'MAX'), help='已确认光比 1:MIN 至 1:MAX')
    parser.add_argument('--lens-range', nargs=2, type=float, metavar=('MIN', 'MAX'), help='已确认焦距区间，单位 mm')
    args = parser.parse_args()
    if args.genre is not None:
        if args.format != 'card' or args.light_range is not None or args.lens_range is not None:
            parser.error('--genre 不接受选卡输出参数')
        render_recommendation(args.genre)
        return True
    if args.select not in {s[0] for s in styles}:
        parser.error('该编号未在此入口注册')
    try:
        print(render_selection(args.select, args.format, args.light_range, args.lens_range))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    return True
