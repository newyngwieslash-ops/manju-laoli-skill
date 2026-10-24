# -*- coding: utf-8 -*-
"""
gate_check.py · 六道闸门校验器（判定口径修正 · 闸门6 扩展素材形态）
用法：python gate_check.py <投喂稿.md> [--model 2.5|2.0|h3] [--assets N] [--mode M0|M1|M2|auto] [--tol 0.8]
设计依据：sd-feed-engine/references/feed-mode-and-gates.md §二（六道闸门）
定位：人工前置闸门的机器化兜底，与总控 scripts/validate_prompt.py（C1~C26＋增量主码 C27~C30 机检）互补。

修正（2026-10-08 · 用户实测反馈）：
  旧版闸门2 用「标准档中值 (need_fast+need_slow)/2」判定念不念得完，
  等于假设演员只能按 4~4.5 字/秒念 → 把大量能快念完的台词误判成"念不完"，
  进而误触发"精简台词"。
  现改为：**判定基准 = 最快档 6 字/秒**（`字数÷6 + 停顿`）。
    镜长 ≥ 该值 → 一定念得完，合规，不得判超载；
    只有连 6 字/秒 都塞不进 → 才是真念不完（WARN）。
    介于两者之间（最快能过、标准档不够）→ 仅 INFO「需快念」，非缺陷、不触发精简。
  语速档只由"节奏维"语气词决定；音质/力度词（压着嗓子/嘶哑/沉声）不必然慢。

闸门 6 扩展（素材形态一致性 · 权威 = 总控 references/asset-delivery-modes.md）：
  本包**不持有图**——图由用户在外部平台生成并持有。素材形态三档 M0/M1/M2（默认 M1）。
  闸门 6 = 6A 编号一致性 + 6B 素材形态一致性：
    未声明形态 → WARN；M0 稿内出现图号 → FAIL（形态违约）；
    M1 有图号但无《素材接线单》→ WARN；稿内图号 ∉ 接线单图号 → FAIL；
    出现"已核验/核对一致"类断言而形态非 M2 → FAIL（虚假核验）。
"""
import re, sys, io, os, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "short-drama-director/scripts"))
from model_contract import WORD_LIMITS

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ---------- 语速表 ----------
# 只有"节奏维"词才真正决定语速档；"压着嗓子/嘶哑/沉声"是音质力度描述，不必然慢。
SPEED_BANDS = [
    (r'耳语|气声|一字一顿|一字一停|一字一句|拖长|断续|哽咽|抽气', 2.5, 3.5, '慢速重音（节奏维慢）'),
    (r'低语|低声|压抑|嘶哑|沉声|沉冷|宣判|喃喃|放缓', 3.5, 4.5, '偏慢'),
    (r'争吵|吼|喊|嚷|咆哮|抢话|慌乱|急促|连珠|语速快', 5.0, 6.0, '快速/争吵/抢话'),
]
SPEED_DEFAULT = (3.5, 6.0, '标准~高速（判定按 6 字/秒）')

PAUSE = [('，', 0.2), ('、', 0.2), ('。', 0.4), ('？', 0.4), ('！', 0.4), ('…', 0.8), ('——', 0.6)]


def parse_units(text):
    """切分投喂单元，返回 [(标题, 代码框正文)]，兼容 ## 【投喂单元...】 / ### 段N... / ### 第N段... / 代码框内含【画幅风格】"""
    unit_hdr_re = re.compile(r'^(?:##\s*【投喂单元[^\n]*|###+\s*(?:第\s*\d+\s*段|段\s*\d+)[^\n]*)', re.M)
    matches = list(unit_hdr_re.finditer(text))
    units = []
    if matches:
        for i, m in enumerate(matches):
            title = m.group(0).lstrip('#').strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            chunk = text[start:end]
            fm = re.search(r'```(?:text|prompt)?\s*\n(.*?)```', chunk, re.S)
            if fm and '【画幅风格】' in fm.group(1):
                units.append((title, fm.group(1)))
            elif '【画幅风格】' in chunk and '【时间轴分镜】' in chunk:
                units.append((title, chunk.strip()))
    if not units:
        # 兜底：直接扫描所有包含【画幅风格】与【时间轴分镜】的代码框或段落
        for idx, fm in enumerate(re.finditer(r'```(?:text|prompt)?\s*\n(.*?)```', text, re.S), 1):
            if '【画幅风格】' in fm.group(1) and '【时间轴分镜】' in fm.group(1):
                units.append((f'段{idx}', fm.group(1)))
    return units


# 兼容三形态时码（MM:SS-MM:SS / Xs-Ys / N-N秒）与全半角【镜头N】及「镜号在前/时码在前」双语序
GC_TIME_RE = re.compile(
    r'(\d{1,2}):(\d{2})(?:[.:](\d{1,2}))?\s*[-~～→]\s*(\d{1,2}):(\d{2})(?:[.:](\d{1,2}))?'
    r'|(\d+(?:\.\d+)?)\s*s\s*[-~～→]\s*(\d+(?:\.\d+)?)\s*s'
    r'|(?:\A|(?<=[\s\[【\]】]))\s*([0-9]|[1-5]\d)(?:\.\d+)?\s*[-~～→]\s*([0-9]|[1-5]\d)(?:\.\d+)?秒',
    re.I)
GC_SHOT_NO_RE = re.compile(r'[\[【]?\s*镜头\s*(\d+)\s*[\]】]?')


def frac_to_sec(frac):
    """秒的小数位 → 秒值（★2026-10-14 Agent 修复：统一小数秒口径）。

    `5`→0.5 · `50`→0.5 · `05`→0.05 —— **按位数换算，不写死 ÷100**。
    原实现写 `fr / 100.0`，把 1 位小数 `.5` 算成 0.05：`00:03.5` → 3.05s。
    闸门 2（字数÷6 对镜长）靠这里的秒值判定，口径错会让边缘稿误放行/误拦截。
    本口径须与总控 `scripts/sd_core.frac_to_sec`、`validate_prompt._frac_to_sec` 三处一致。
    """
    if not frac:
        return 0.0
    return int(frac) / (10 ** len(frac))


def parse_shots(body):
    """解析镜行，返回 [(镜号, 起秒, 止秒, 全行)]，兼容 MM:SS(.s) / Xs-Ys / N-N秒 与全半角镜号。"""
    shots = []
    auto_no = 0
    for line in body.splitlines():
        tm = GC_TIME_RE.search(line)
        if not tm:
            continue
        if tm.group(1) is not None:
            s = int(tm.group(1)) * 60 + int(tm.group(2)) + frac_to_sec(tm.group(3))
            e = int(tm.group(4)) * 60 + int(tm.group(5)) + frac_to_sec(tm.group(6))
        elif tm.group(7) is not None:
            s, e = float(tm.group(7)), float(tm.group(8))
        else:
            s, e = float(tm.group(9)), float(tm.group(10))
        sm = GC_SHOT_NO_RE.search(line)
        auto_no += 1
        no = int(sm.group(1)) if sm else auto_no
        shots.append((no, s, e, line))
    return shots


def parse_lines(body):
    """解析台词，返回 [(角色, 语气, 台词, 全行)]"""
    out = []
    # 修正：引号定界改非贪婪 `(.*?)"】` —— 台词内嵌引号（如「先认一句"我做得够好了"」）
    # 会把旧的 `[^"]*` 截断或整句漏检（静默失检）。新式以「"】」为唯一收尾锚点。
    for m in re.finditer(r'台词：【([^（(]*)（([^）)]*)）：?"(.*?)"】', body):
        out.append((m.group(1).strip(), m.group(2).strip(), m.group(3), m.group(0)))
    # 无语气位的台词（违规）
    for m in re.finditer(r'台词：【([^（(]*)："(.*?)"】', body):
        out.append((m.group(1).strip(), '', m.group(2), m.group(0)))
    return out


# ---------- 闸门 6B · 素材形态（权威 = 总控 references/asset-delivery-modes.md） ----------
MODE_DECL = re.compile(r'素材形态[：:]\s*[（(]?\s*(M[012])')
WIRING_HEAD = re.compile(r'^##\s*素材接线单[^\n]*\n', re.M)
# "已核验/核对一致"类虚假核验断言（排除否定与禁止语境）
FAKE_VERIFY = re.compile(r'(?<![未不])已核验|(?<![未不])核对一致|(?<![未不])核验通过|已与《?资产图册》?一致')
NEG_CTX = re.compile(r'未|不|禁止|不得|没有|无核验|仅适用|非')


def split_wiring(text):
    """把整份交付拆成 (提示词正文, 接线单段)。接线单段不计入稿内图号判定。"""
    m = WIRING_HEAD.search(text)
    if not m:
        return text, ''
    rest = text[m.end():]
    nxt = re.search(r'^##\s', rest, re.M)
    end = m.end() + nxt.start() if nxt else len(text)
    return text[:m.start()] + text[end:], text[m.start():end]


def check_asset_mode(text, mode_arg, fails, warns):
    """闸门 6B：素材形态一致性。返回实际生效形态。"""
    decl = MODE_DECL.search(text)
    if mode_arg in (None, '', 'auto'):
        if decl:
            mode = decl.group(1)
        else:
            mode = 'M1'
            warns.append('闸门6B 未声明素材形态（首行应写「素材形态：M0/M1/M2」）——'
                         '形态未定，本次按默认 M1 判定；未声明不得交付')
    else:
        mode = mode_arg.upper()
        if not decl:
            warns.append(f'闸门6B 未声明素材形态，本次按命令行 --mode {mode} 判定——'
                         '交付稿首行仍须补声明')
        elif decl.group(1) != mode:
            warns.append(f'闸门6B 声明形态 {decl.group(1)} 与 --mode {mode} 不一致，'
                         f'按声明 {decl.group(1)} 判定——请核对')
            mode = decl.group(1)

    prompt_text, wiring_text = split_wiring(text)
    figs_prompt = sorted(set(int(x) for x in re.findall(r'图(\d+)', prompt_text)))
    figs_wiring = sorted(set(int(x) for x in re.findall(r'图(\d+)', wiring_text)))

    if mode == 'M0' and figs_prompt:
        fails.append(f'闸门6B 形态违约：声明 M0（纯提示词）却出现图号 {figs_prompt}'
                     '——图号槽位与 M0 互斥，须删净或改声明 M1')
    if mode == 'M1' and figs_prompt:
        if not wiring_text:
            warns.append(f'闸门6B 形态违约：M1 稿件引用图号 {figs_prompt} 但未附《素材接线单》'
                         '——接线单是 M1 交付必备件（§ 素材接线单）')
        else:
            oob = [f for f in figs_prompt if f not in figs_wiring]
            if oob:
                fails.append(f'闸门6B 稿内图号 {oob} 不在《素材接线单》内'
                             '——用户会去挂一张不存在的图')
            if '不控制' not in wiring_text:
                warns.append('闸门6B 接线单缺少「不控制什么」列/说明'
                             '——一张图被当多张用是主要污染源')
    if mode in ('M0', 'M1'):
        for i, line in enumerate(text.split('\n'), 1):
            if FAKE_VERIFY.search(line) and not NEG_CTX.search(line):
                fails.append(f'闸门6B 虚假核验断言（第 {i} 行，形态 {mode}）'
                             '——本包看不到图，不得声称已核验/与资产图册一致')
                break
    return mode


def speech_seconds(line, tone):
    """估算台词秒数 → (最快可行, 最慢舒适, 字数, lo, hi)
    need_fast = n/hi + pause  ← ★判定基准（V7.3.0：hi 通常 = 6 字/秒）
    need_slow = n/lo + pause  ← 舒适参考
    """
    lo, hi = SPEED_DEFAULT[0], SPEED_DEFAULT[1]
    for pat, a, b, _ in SPEED_BANDS:
        if re.search(pat, tone):
            lo, hi = a, b
            break
    n = len(re.findall(r'[\u4e00-\u9fff\w]', line))
    pause = sum(line.count(c) * p for c, p in PAUSE)
    return n / hi + pause, n / lo + pause, n, lo, hi


def self_test():
    """闸门自身解析自检（★2026-10-14 Agent 新增）。

    锁两类「静默失效」：① 小数秒解算（`.5` 曾被算成 0.05s）；② 投喂单元切分。
    这两类一旦失手，闸门会照打 PASS——假 PASS 比假 FAIL 危险一个量级。
    """
    ok = 0
    if frac_to_sec('5') != 0.5 or frac_to_sec('50') != 0.5 or frac_to_sec('05') != 0.05 \
       or frac_to_sec(None) != 0.0:
        print('FAIL self-test: frac_to_sec 位数换算错误（.5 应为 0.5s，.05 应为 0.05s）'); ok = 1
    sh = parse_shots('【时间轴分镜】\n'
                     '00:00-00:04 [镜头1] 中景。甲。\n'
                     '00:04-00:08 [镜头2] 近景。甲。\n'
                     '00:08-00:10.5 [镜头3] 特写。甲。\n'
                     '00:10.5-00:15 [镜头4] 全景。甲。')
    if len(sh) != 4:
        print(f'FAIL self-test: parse_shots 应解析 4 镜，实得 {len(sh)}（丢镜即本用例拦截目标）'); ok = 1
    elif abs(sh[2][2] - 10.5) > 1e-9 or abs(sh[3][1] - 10.5) > 1e-9:
        print(f'FAIL self-test: 00:10.5 应解为 10.5s（旧缺陷为 10.05s），实得 {sh[2][2]}'); ok = 1
    unit_md = ('## 【投喂单元 1/1 · 段1】\n'
               '```text\n【画幅风格】16:9 横屏\n【时间轴分镜】\n'
               '00:00-00:04 [镜头1] 中景 · 平视 · 固定。甲开口。声音：无。台词：【甲：“你好。”】\n'
               '```\n')
    us = parse_units(unit_md)
    if len(us) != 1 or '【画幅风格】' not in us[0][1]:
        print(f'FAIL self-test: parse_units 应切出 1 个投喂单元，实得 {len(us)}'); ok = 1
    if not ok:
        print('[+] gate_check self-test PASSED')
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path', nargs='?')
    ap.add_argument('--model', default='2.5')
    ap.add_argument('--assets', type=int, default=9, help='项目资产库总图数')
    ap.add_argument('--mode', default='auto', choices=['auto', 'M0', 'M1', 'M2', 'm0', 'm1', 'm2'],
                    help='素材形态（V7.3.0）：auto=按交付稿首行「素材形态：Mx」声明判定，'
                         '未声明时按默认 M1 并告警。权威 = references/asset-delivery-modes.md')
    ap.add_argument('--tol', type=float, default=0.8,
                    help='闸门2 判定容差(s)：V7.3.0 以最快档 6 字/秒为判定基准，'
                         '仅当「字数÷6 + 停顿 > 镜长 + tol」才判真念不完。默认 0.8')
    ap.add_argument('--self-test', action='store_true')
    a = ap.parse_args()

    if a.self_test:
        sys.exit(self_test())
    if not a.path:
        ap.print_help(); sys.exit(2)

    text = open(a.path, encoding='utf-8').read()
    units = parse_units(text)
    if not units:
        print('未找到投喂单元（## 【投喂单元 N/M】格式）'); sys.exit(2)

    print(f'=== 六道闸门校验 · {os.path.basename(a.path)} · model={a.model} ===')

    warns, fails, infos = [], [], []
    mode = check_asset_mode(text, a.mode, fails, warns)

    print(f'投喂单元：{len(units)} 段  |  闸门2 判定基准：最快档 6 字/秒（V7.3.0）'
          f'  |  素材形态：{mode}（闸门6B · V7.3.0）\n')

    # ---- 闸门 0 · 结构完整性自检（防字符损坏导致下游全漏检）----
    for ui, (title, body) in enumerate(units, 1):
        for m in re.finditer(r'【[^】\n]*$', body, re.M):
            fails.append(f'闸门0 段{ui}：【 未闭合（行尾缺 】）→ {m.group(0)[:40]}')
        if body.count('【') != body.count('】'):
            fails.append(f'闸门0 段{ui}：【/】数量不等（{body.count("【")} vs {body.count("】")}）')
        for m in re.finditer(r'台词：【[^】\n]*\n', body):
            fails.append(f'闸门0 段{ui}：台词行未见 】 收尾 → {m.group(0)[:40]}')
        # 镜号连续
        nums = [int(x) for x in GC_SHOT_NO_RE.findall(body)]
        if nums and nums != list(range(1, len(nums) + 1)):
            fails.append(f'闸门0 段{ui}：镜号不连续 {nums}')
        # 七段式必备字段（2026-10-09：【接续状态】尾行已废止，从必备列表移除）
        for f in ['【画幅风格】', '【场景资产】', '【核心人物】', '【站位声明】', '【时间轴分镜】']:
            if f not in body:
                fails.append(f'闸门0 段{ui}：缺字段 {f}')
        if '【接续状态】' in body:
            fails.append(f'闸门0 段{ui}：出现已废止的【接续状态】栏（2026-10-09 废止，机检 C11 反转为残留拦截）')

    for ui, (title, body) in enumerate(units, 1):
        shots = parse_shots(body)
        lines = parse_lines(body)
        dur = (shots[-1][2] - shots[0][1]) if shots else 0
        chars = len(body)
        figs = sorted(set(int(x) for x in re.findall(r'图(\d+)', body)))
        print(f'--- 段{ui}: {title}')
        print(f'    镜数={len(shots)}  段长={dur}s  字数={chars}  引用图号={figs}')

        # 闸门1 节奏档位：10s 以上只有 1-2 镜
        if dur >= 10 and len(shots) <= 2:
            warns.append(f'闸门1 段{ui}：{dur}s 只有 {len(shots)} 镜，需慢节奏白名单或补标点镜')
        # 闸门1b 镜长分布
        if shots:
            lens = [e - s for _, s, e, _ in shots]
            if len(lens) >= 4:
                from collections import Counter
                top = Counter(lens).most_common(1)[0]
                if top[1] / len(lens) >= 0.7:
                    warns.append(f'闸门1 段{ui}：镜长雷同（{top[0]}s × {top[1]}/{len(lens)}）')

        # 闸门2 台词时长（以最快档 6 字/秒为判定基准）
        # ★ 末镜让出「末 1 秒硬定格」（2026-10-13 粉丝实测修复）：
        #   模型优先级 = **先把台词说完** > 执行定格指令（实测：段1 人声说到最后一帧、
        #   画面末 1 秒运动量与全片持平 = 根本没定格；段2 台词提前 0.65s 念完 → 收住了）。
        #   硬要求模型「边说话边定格」= 视听分裂（嘴在动、画面冻住）。
        #   故末镜有效可说话时长 = 镜长 − 1 秒，按此判定；塞不下就前移台词 / 加长末镜 / 末镜改无台词。
        last_end = shots[-1][2] if shots else None
        for role, tone, line, _ in lines:
            if not tone:
                fails.append(f'闸门2 段{ui}：台词缺语气位「{role}」（C16b）')
                continue
            need_fast, need_slow, n, lo, hi = speech_seconds(line, tone)
            mid = (need_fast + need_slow) / 2   # 舒适中值，仅作 INFO 参考
            # 找承载该台词的镜长
            hit = None
            is_last = False
            for _, s, e, ln in shots:
                if line in ln:
                    hit = e - s
                    is_last = (e == last_end)
                    break
            if hit is None:
                continue
            budget = hit - 1 if is_last else hit
            tail_note = f'（末镜已让出末 1 秒定格期，可说话 {budget}s）' if is_last else ''
            if need_fast > budget + a.tol:
                # 连最快档都塞不进 → 真念不完
                warns.append(
                    f'闸门2 段{ui}：台词「{line[:12]}…」{n}字/{tone} 连最快 {hi} 字/秒都需 '
                    f'{need_fast:.1f}s，可用仅 {budget}s{tail_note} → 真念不完'
                    + ('（★末镜：定格期被台词占用 → 画面定格而人在说话，须前移台词 / 加长末镜 / 末镜改无台词）'
                       if is_last else ''))
            elif mid > budget + a.tol:
                # 最快能过、标准档不够 → 仅需快念，非缺陷
                infos.append(
                    f'闸门2 段{ui}：台词「{line[:12]}…」{n}字 标准档需 {mid:.1f}s / '
                    f'最快 {need_fast:.1f}s，可用 {budget}s{tail_note} → 需快念（非缺陷，不触发精简）')

        # 闸门3 字数（★ 2026-10-13：按模型分档 —— 2.5 可吃更长提示词）
        w_soft, w_hard = WORD_LIMITS[a.model]
        if chars > w_hard:
            fails.append(f'闸门3 段{ui}：字数 {chars} > {w_hard}（model={a.model} 硬上限），必须压缩')
        elif chars > w_soft:
            warns.append(f'闸门3 段{ui}：字数 {chars} 落在 {w_soft + 1}~{w_hard}（model={a.model}），建议压一轮')

        # 闸门4 可投喂语义
        for bad in ['接下一大分镜', '接下一段', '接分镜', '承接上一段', '接上段']:
            if bad in body:
                fails.append(f'闸门4 段{ui}：含交接话术「{bad}」')
        # 参数行应在代码框外
        for bad in ['9:16', '16:9', '21:9', '分辨率', 'aspect_ratio']:
            if re.search(r'(?<!【画幅风格】)…?' + re.escape(bad), body) and bad in ('aspect_ratio', '分辨率'):
                warns.append(f'闸门4 段{ui}：参数「{bad}」疑似留在代码框内')

        # 闸门5 单组图片数
        if len(figs) > 9:
            fails.append(f'闸门5 段{ui}：单段引用 {len(figs)} 个图号 > 9')

        # 闸门6A 编号一致性（图号是否在资产库范围内）
        oob = [f for f in figs if f > a.assets]
        if oob:
            fails.append(f'闸门6A 段{ui}：引用图号 {oob} 超出资产库（共 {a.assets} 图）')

    print()
    print('=== 结果 ===')
    if fails:
        print(f'FAIL {len(fails)} 条：')
        for x in fails:
            print('  ✗', x)
    if warns:
        print(f'WARN {len(warns)} 条：')
        for x in warns:
            print('  !', x)
    if infos:
        print(f'INFO {len(infos)} 条（非缺陷，仅提示需快念）：')
        for x in infos:
            print('  i', x)
    if not fails and not warns:
        print('  六道闸门全过（0 FAIL 0 WARN）')
    print(f'\n汇总：FAIL={len(fails)}  WARN={len(warns)}  INFO={len(infos)}  '
          f'素材形态={mode}（闸门6B）')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
