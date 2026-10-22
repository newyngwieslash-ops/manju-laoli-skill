"""Read full style cards from the authoritative Markdown; never write project state."""
import argparse
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import sys

# Compatibility IDs resolve to one maintained core, not extra cards.
CARD_ALIASES = {28: 68}
INHERITED_RANGE_IDS = (36, 68)

STYLE_DIR = Path(__file__).resolve().parents[1] / 'references' / 'style-bible'


def _section(text, predicate):
    sections = re.split(r'(?m)(?=^## )', text)
    matches = [s.strip() for s in sections if s.strip() and predicate(s.splitlines()[0])]
    if len(matches) != 1:
        raise ValueError('未找到唯一完整卡；请按参数库补录模板人工组装，不生成伪造参数')
    return matches[0]


def load_card(style_id):
    if type(style_id) is not int or style_id <= 0:
        raise ValueError("风格编号必须为正整数，不接受字符串或布尔值")
    requested_id = style_id
    style_id = CARD_ALIASES.get(style_id, style_id)
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
    if len(blocks) != 2 or not blocks[0].startswith('【STYLE｜') or not blocks[1].startswith('【PERFORMANCE｜'):
        raise ValueError('成品块必须包含 STYLE 和 PERFORMANCE 两段')
    if style_id in INHERITED_RANGE_IDS and [len(b.splitlines()) for b in blocks] != [10, 4]:
        raise ValueError(f'编号 {style_id} 必须保持 STYLE 九行和 PERFORMANCE 三行')
    if style_id in INHERITED_RANGE_IDS:
        for label, token in (("影调区间：光比 ", "{{LIGHT_RANGE}}"),
                             ("光学区间：镜头 ", "{{LENS_RANGE}}")):
            if sum(b.count(token) for b in blocks) != 1 or not any(
                    line.startswith(label + token) for line in blocks[0].splitlines()):
                raise ValueError(f"编号 {style_id} 的项目区间占位符缺失、重复或槽位错误")
    if requested_id != style_id:
        card = f'> 兼容编号 {requested_id} → 核心编号 {style_id}；同一卡，不另计数量。\n\n' + card
    return card, block, '\n\n'.join(blocks)


def _range(values, unit):
    if not isinstance(values, (list, tuple)) or len(values) != 2:
        raise ValueError('区间必须恰好提供 MIN MAX 两个值')
    exact = []
    for value in values:
        # Bound conversion cost by the existing 42-character prompt line budget.
        # This is a serialization limit, not a claim about physical camera limits.
        token = str(value)
        if len(token) > 64:
            raise ValueError('数值文本过长，无法满足成品块行宽限制')
        try:
            number = Decimal(token)
        except InvalidOperation as exc:
            raise ValueError('区间只接受有限正数') from exc
        if not number.is_finite() or number <= 0:
            raise ValueError('区间只接受有限正数')
        if abs(number.adjusted()) > 42 or len(number.as_tuple().digits) > 42:
            raise ValueError('极端数值无法满足成品块行宽限制')
        exact.append(number)
    if exact[0] > exact[1]:
        raise ValueError('区间必须满足 MIN <= MAX')
    if unit == 'mm' and any(v != v.to_integral_value() for v in exact):
        raise ValueError('现有 C23 焦距区间只支持整数 mm，请使用项目确认的整数区间')
    def plain(number):
        value = format(number, 'f')
        return value.rstrip('0').rstrip('.') if '.' in value else value
    return '[' + ', '.join('1:' + plain(v) if unit == 'ratio' else plain(v) + 'mm'
                            for v in exact) + ']'


def render_selection(style_id, output='card', light=None, lens=None):
    if output not in ('card', 'prompt'):
        raise ValueError('输出格式仅支持 card 或 prompt')
    card, block, prompt = load_card(style_id)
    style_id = CARD_ALIASES.get(style_id, style_id)
    if output == 'card':
        if light is not None or lens is not None:
            raise ValueError('区间参数仅用于 --format prompt，避免误以为已经应用')
        return card + '\n\n' + block
    if style_id in INHERITED_RANGE_IDS:
        if light is None or lens is None:
            raise ValueError(f'编号 {style_id} 投喂块需要项目已确认的 --light-range 和 --lens-range；未知值不自动补造')
        prompt = prompt.replace('{{LIGHT_RANGE}}', _range(light, 'ratio'))
        prompt = prompt.replace('{{LENS_RANGE}}', _range(lens, 'mm'))
    elif light is not None or lens is not None:
        raise ValueError('区间输入仅适用于项目继承卡（36、68及别名28）；其他卡保持既有正文')
    if style_id in INHERITED_RANGE_IDS:
        if '{{' in prompt or any(len(line) > 42 for line in prompt.splitlines()):
            raise ValueError('数值区间超出成品块 42 字行宽，无法输出；请核对项目参数')
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
    parser.add_argument('--light-range', nargs=2, type=str, metavar=('MIN', 'MAX'), help='已确认光比 1:MIN 至 1:MAX')
    parser.add_argument('--lens-range', nargs=2, type=str, metavar=('MIN', 'MAX'), help='已确认焦距区间，单位 mm')
    args = parser.parse_args()
    if args.genre is not None:
        if args.format != 'card' or args.light_range is not None or args.lens_range is not None:
            parser.error('--genre 不接受选卡输出参数')
        render_recommendation(args.genre)
        return True
    registered = {s[0] for s in styles}
    if args.select not in registered and CARD_ALIASES.get(args.select) not in registered:
        parser.error('该编号未在此入口注册')
    try:
        print(render_selection(args.select, args.format, args.light_range, args.lens_range))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    return True
