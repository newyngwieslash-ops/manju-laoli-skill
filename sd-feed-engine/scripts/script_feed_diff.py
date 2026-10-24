#!/usr/bin/env python3
"""Exact dialogue conservation across script → storyboard → feed.
JSON uses existing dialogue_id/speaker_id/voice_id/exact_text dialogue_slices.
Text compatibility requires an explicit cast (--names); no zero-parse success.
"""
import argparse
import json
from pathlib import Path
import re
import sys


def structured(data):
    if not isinstance(data,dict):raise ValueError('台词数据必须为对象')
    payload=data.get('payload',data)
    if not isinstance(payload,dict):raise ValueError('payload 必须为对象')
    if 'dialogues' in payload:
        rows=payload['dialogues']
    else:
        segments=payload.get('segments')
        if not isinstance(segments,list):raise ValueError('缺少 dialogues 或 segments/dialogue_slices')
        rows=[]
        for segment in segments:
            if not isinstance(segment,dict) or not isinstance(segment.get('dialogue_slices'),list):raise ValueError('每段必须显式列 dialogue_slices')
            rows.extend(segment['dialogue_slices'])
    if not isinstance(rows,list):raise ValueError('台词必须为列表')
    if not rows and payload.get('dialogue_free') is not True:raise ValueError('零台词必须显式声明 dialogue_free=true')
    out=[];seen=set();pending=None
    for row in rows:
        if not isinstance(row,dict) or any(not isinstance(row.get(k),str) or not row[k].strip() for k in ('dialogue_id','speaker_id','voice_id','exact_text')):
            raise ValueError('台词必须有非空 dialogue_id/speaker_id/voice_id/exact_text')
        key=(row['dialogue_id'],row['speaker_id'],row['voice_id'])
        integrity=row.get('integrity','WHOLE')
        if integrity=='WHOLE':
            if pending or key[0] in seen:raise ValueError('台词重复或拆句链未结束')
            out.append((*key,row['exact_text']));seen.add(key[0])
        elif integrity=='CLAUSE_HEAD':
            if pending or key[0] in seen:raise ValueError('重复拆句起点')
            pending=[key,row['exact_text']]
        elif integrity in ('CLAUSE_MIDDLE','CLAUSE_TAIL'):
            if not pending or pending[0]!=key:raise ValueError('拆句说话人/声线/ID或顺序不一致')
            pending[1]+=row['exact_text']
            if integrity=='CLAUSE_TAIL':
                out.append((*key,pending[1]));seen.add(key[0]);pending=None
        else:raise ValueError('未知 integrity')
    if pending:raise ValueError('拆句链缺尾句')
    return out


def text_rows(path,names):
    if not names:raise ValueError('Markdown 兼容模式必须提供 --names；推荐使用结构化 JSON')
    text=Path(path).read_text(encoding='utf-8')
    pattern='|'.join(re.escape(x.strip()) for x in names.split(',') if x.strip())
    if not pattern:raise ValueError('names 不能为空')
    rows=[]
    for line in text.splitlines():
        # Dialogue cue can occur inline in a shot, or as a script line.
        if '台词：' in line:line=line.split('台词：',1)[1]
        m=re.search(r'(?:^|【)('+pattern+r')(?:[（(][^）)]*[）)])?\s*[：:]\s*(.+)',line)
        if m:
            body=m.group(2).strip().rstrip('。')
            body=body.rstrip('】').strip().strip('“”"')
            if not body:raise ValueError('空台词')
            rows.append((str(len(rows)+1),m.group(1),'text-unverified',body))
    if not rows:raise ValueError('零解析，不能证明台词守恒')
    return rows


def read_rows(path,names=None):
    path=Path(path)
    return structured(json.loads(path.read_text(encoding='utf-8'))) if path.suffix.lower()=='.json' else text_rows(path,names)


def compare(before,after,approvals=(),phase='script-to-storyboard'):
    expected=list(before)
    used=set()
    for record in approvals:
        if not isinstance(record,dict):raise ValueError('删改记录必须为对象')
        if record.get('phase')!=phase:continue
        did=record.get('dialogue_id')
        matches=[i for i,row in enumerate(expected) if row[0]==did]
        if did in used or len(matches)!=1:raise ValueError('删改记录 ID 重复或不存在')
        used.add(did);i=matches[0];row=expected[i]
        if record.get('status')!='approved' or not record.get('approval_ref') or not record.get('reason'):
            raise ValueError('删改必须有批准状态、来源引用和理由；程序不代替批准')
        if record.get('before')!=row[3] or record.get('speaker_id')!=row[1]:raise ValueError('批准记录与源台词不符')
        replacement=record.get('after')
        if replacement is None:expected.pop(i)
        elif isinstance(replacement,str) and replacement:expected[i]=(*row[:3],replacement)
        else:raise ValueError('after 必须为非空文本或 null（明确删除）')
    if expected!=after:
        raise ValueError(f'{phase}: 台词 ID/说话人/声线/文本/顺序/次数不守恒（上游{len(expected)}，下游{len(after)}）')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--script',required=True)
    ap.add_argument('--storyboard',help='提供后分别检查剧本→分镜与分镜→投喂')
    ap.add_argument('--feed',required=True)
    ap.add_argument('--names',help='Markdown 兼容模式的明确角色清单，无默认姓名')
    ap.add_argument('--approvals',help='显式批准删改记录 JSON 列表')
    args=ap.parse_args()
    try:
        records=json.loads(Path(args.approvals).read_text(encoding='utf-8')) if args.approvals else []
        if not isinstance(records,list):raise ValueError('approvals 必须为列表')
        if any(not isinstance(r,dict) or r.get('phase') not in ('script-to-storyboard','storyboard-to-feed','script-to-feed') for r in records):raise ValueError('未知批准记录阶段')
        paths=[args.script,args.storyboard,args.feed] if args.storyboard else [args.script,args.feed]
        rows=[read_rows(p,args.names) for p in paths]
        phases=['script-to-storyboard','storyboard-to-feed'] if args.storyboard else ['script-to-feed']
        if any(r['phase'] not in phases for r in records):raise ValueError('批准记录阶段未参与本次校验')
        for i,phase in enumerate(phases):compare(rows[i],rows[i+1],records,phase)
    except (ValueError,OSError) as exc:ap.error(str(exc))
    print('[PASS] 台词逻辑守恒；未进行人工语义或音视频验收')
    return 0

if __name__=='__main__':sys.exit(main())
