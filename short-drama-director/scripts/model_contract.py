"""Single project-policy source. No provider limit is certified by this file."""
import argparse
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'references/model-capabilities.json'
PROFILES=json.loads(CONFIG.read_text(encoding='utf-8'))['profiles']
MODEL_LIMITS={k:v['project_policy']['max_segment_seconds'] for k,v in PROFILES.items()}
WORD_LIMITS={k:(v['project_policy']['soft_chars'],v['project_policy']['hard_chars']) for k,v in PROFILES.items()}
START='<!-- model-contract:start -->'
END='<!-- model-contract:end -->'

def render():
    lines=[START,'模型能力与字数策略唯一数据源：`references/model-capabilities.json`（通过 `scripts/model_contract.py --write` 更新本表）。',
           '以下数字仅保留既有项目校验策略；官方 provider/model/task_mode 限制均待核，不能作为平台能力承诺。模型必须由用户选择，不默认。',
           '| 模型 | 项目段长上限 | 字符软/硬预算 | 官方证据状态 |', '|---|---|---|---|']
    for model,p in PROFILES.items():
        policy=p['project_policy'];lines.append(f"| {model} | {policy['max_segment_seconds']}s | {policy['soft_chars']}/{policy['hard_chars']} | 待核；非官方限制 |")
    lines += ['时长与字符预算是不同检查维度；不强制吃满段长，不据此改写导演切镜策略。H3 编译尚不支持，必须走独立适配流程；不得输出 Seedance 格式冒充 H3。',END]
    return '\n'.join(lines)

def sync(write=False):
    errors=[]
    for path in (ROOT/'SKILL.md',ROOT/'references/model-adapters.md'):
        text=path.read_text(encoding='utf-8')
        if START not in text:
            if write:path.write_text(text+'\n\n'+render()+'\n',encoding='utf-8')
            else:errors.append(str(path))
        else:
            start=text.index(START);end=text.index(END,start)+len(END)
            if text[start:end]!=render():
                if write:path.write_text(text[:start]+render()+text[end:],encoding='utf-8')
                else:errors.append(str(path))
    return errors

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--write',action='store_true');args=parser.parse_args()
    errors=sync(args.write)
    if errors:parser.error('模型策略生成表过期：'+', '.join(errors))
    print('model contract source/doc consistency PASS; official limits pending')
