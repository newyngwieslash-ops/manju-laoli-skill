"""Offline project contract: explicit locks, segment scope and existing state handoffs.
Validating declarations is not visual inspection or user approval.
"""
from decimal import Decimal, InvalidOperation
import sys
import json
import hashlib
from pathlib import Path
import re

SUITE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SUITE / 'sd-feed-engine/scripts'))
from script_feed_diff import structured

LOCKS = ('track','source','model','aspect','delivery','seam','style_card','asset_mode')


def seconds(value):
    if isinstance(value, bool): raise ValueError('时间不能为布尔值')
    try: n=Decimal(str(value))
    except InvalidOperation as exc: raise ValueError('时间必须为有限数值') from exc
    if not n.is_finite() or n < 0: raise ValueError('时间必须为有限非负值')
    return n


def clock(value):
    n=seconds(value); minutes=int(n//60); rest=n-minutes*60
    token=format(rest,'f').rstrip('0').rstrip('.') if '.' in format(rest,'f') else str(rest)
    return f'{minutes:02d}:'+token.zfill(2 if '.' not in token else len(token)+max(0,2-len(token.split('.')[0])))


def validate_state(state):
    errors=[]
    if not isinstance(state,dict): return ['项目必须为对象']
    receipt=state.get('receipt')
    if receipt is not None and (not isinstance(receipt,dict) or any(not isinstance(receipt.get(k,[]),list) or any(not isinstance(v,str) for v in receipt.get(k,[])) for k in ('read_refs','active_plugins','fingerprints'))):
        errors.append('receipt 必须为对象且各字段为字符串列表')
    locks=state.get('locks')
    if not isinstance(locks,dict): return ['缺少 locks']
    for key in LOCKS:
        if not isinstance(locks.get(key),str) or not locks[key].strip(): errors.append(f'缺少锁 locks.{key}')
    for key,allowed in {'track':('1','2','3','4'),'source':('1','2','3','4'),'delivery':('1','2','3'),'seam':('1','2','3','4')}.items():
        if locks.get(key) not in allowed:errors.append(f'未知锁值 {key}')
    if locks.get('confirmed') is not True: errors.append('locks.confirmed 必须明确为 true；模板不是确认')
    if locks.get('model') not in ('2.0','2.5','h3'): errors.append('未知模型')
    if locks.get('aspect') not in ('16:9','9:16','21:9'): errors.append('未知画幅')
    if locks.get('asset_mode') not in ('M0','M1','M2'): errors.append('未知素材形态')
    if not isinstance(state.get('world_anchor'),dict) or not state['world_anchor'].get('era_anchor'):
        errors.append('world_anchor.era_anchor 必须明确，不能默认现代')
    maps={}
    for key in ('characters','scenes','props'):
        maps[key]=state.get(key)
        if not isinstance(maps[key],dict): errors.append(f'{key} 必须为对象');maps[key]={}
        for name,asset in maps[key].items():
            if not isinstance(asset,dict): errors.append(f'{key}.{name} 必须为对象');continue
            status=asset.get('asset_status',{})
            if not isinstance(status,dict): errors.append(f'{name}.asset_status 必须为对象');continue
            for flag in ('generated','accessible','inspected','approved'):
                if flag in status and type(status[flag]) is not bool: errors.append(f'{name}.{flag} 必须为布尔值')
            if status.get('inspected') and not (status.get('accessible') and status.get('inspection_ref')):
                errors.append(f'{name} inspected 需要 accessible 与 inspection_ref')
            if status.get('approved') and not (status.get('inspected') and status.get('approval_ref')):
                errors.append(f'{name} approved 需要 inspected 与 approval_ref')
            if locks.get('asset_mode')=='M2' and asset.get('fig_no') and not status.get('approved'):
                errors.append(f'{name} M2 图号必须有明确检查/批准记录')
    asset_ids=[a.get('id') for table in maps.values() for a in table.values() if isinstance(a,dict)]
    if any(not isinstance(x,str) or not x for x in asset_ids) or len(set(asset_ids))!=len(asset_ids):errors.append('资产 ID 必须非空且全局唯一')
    segments=state.get('segments')
    if not isinstance(segments,list) or not segments: return errors+['segments 必须为非空列表']
    seen=set();prev=None;prev_sid=None
    for seg in segments:
        if not isinstance(seg,dict): errors.append('段必须为对象');continue
        sid=seg.get('seg_id')
        if not isinstance(sid,str) or not sid or sid in seen: errors.append('段编号缺失或重复')
        else:seen.add(sid)
        if seg.get('scene') not in maps['scenes']:errors.append(f'{sid} 未知场景')
        for key,table in (('cast','characters'),('props','props')):
            vals=seg.get(key)
            if not isinstance(vals,list) or any(not isinstance(x,str) for x in vals): errors.append(f'{sid}.{key} 必须显式列出（可为空）');continue
            if len(set(vals))!=len(vals) or any(x not in maps[table] for x in vals):errors.append(f'{sid}.{key} 重复或未知实体')
        allowed_refs=set(seg.get('cast',[])+seg.get('props',[])+[seg.get('scene')]) if isinstance(seg.get('cast'),list) and isinstance(seg.get('props'),list) else set()
        for sh in seg.get('shots',[]):
            if not isinstance(sh,dict):continue
            for ref in re.findall(r'@(?:PRP-)?([^\s，。；：（()）]+)',sh.get('action','')):
                if ref not in allowed_refs:errors.append(f'{sid} 镜头引用未在本段登记：{ref}')
        for key in ('entry_state','exit_state'):
            snapshot=seg.get(key)
            if not isinstance(snapshot,dict) or not snapshot: errors.append(f'{sid}.{key} 必须为非空连续性快照');continue
            allowed=set(seg.get('cast',[])+seg.get('props',[])+[seg.get('scene')]) if isinstance(seg.get('cast'),list) and isinstance(seg.get('props'),list) else set()
            if set(snapshot)!=allowed: errors.append(f'{sid}.{key} 必须覆盖本段全部且仅有实体')
            if any(not isinstance(v,dict) or not v or any(not isinstance(x,str) or not x.strip() for x in v.values()) for v in snapshot.values()):errors.append(f'{sid}.{key} 实体状态不能为空')
        entry=seg.get('entry_state',{});out=seg.get('exit_state',{})
        changes=seg.get('state_changes',[])
        if not isinstance(changes,list):errors.append(f'{sid}.state_changes 必须为列表');changes=[]
        shots=seg.get('shots')
        if not isinstance(shots,list) or not shots: errors.append(f'{sid}.shots 不能为空');continue
        shotids=[s.get('no') for s in shots if isinstance(s,dict)]
        if len(set(shotids))!=len(shotids) or any(type(x) is not int or x<=0 for x in shotids):errors.append(f'{sid} 镜号必须唯一正整数')
        for change in changes:
            if not isinstance(change,dict) or change.get('phase') not in ('boundary','within'):
                errors.append(f'{sid} 变化记录阶段无效');continue
            before,after=(prev or {},entry) if change['phase']=='boundary' else (entry,out)
            entity=change.get('entity')
            if not isinstance(before,dict) or not isinstance(after,dict):continue
            if entity not in before.keys()|after.keys() or before.get(entity)==after.get(entity) or change.get('before')!=before.get(entity) or change.get('after')!=after.get(entity):
                errors.append(f'{sid} 变化记录与实际出入状态不符')
            if not isinstance(change.get('reason'),str) or not change['reason'].strip():errors.append(f'{sid} 变化缺理由')
            if change['phase']=='boundary' and (prev is None or change.get('handoff_ref')!=f'{prev_sid}→{sid}'):
                errors.append(f'{sid} 交接引用须指向相邻段 {prev_sid}→{sid}')
            if change['phase']=='within' and change.get('shot_no') not in shotids:errors.append(f'{sid} 变化引用未知镜头')
        for before,after,phase in ((prev or {},entry,'boundary'),(entry,out,'within')):
            if not isinstance(before,dict) or not isinstance(after,dict):continue
            for entity in before.keys()|after.keys():
                if prev is None and phase=='boundary':continue
                if before.get(entity)!=after.get(entity):
                    matching=[c for c in changes if isinstance(c,dict) and c.get('entity')==entity and c.get('phase')==phase
                              and c.get('before')==before.get(entity) and c.get('after')==after.get(entity)
                              and isinstance(c.get('reason'),str) and c['reason'].strip()
                              and (c.get('shot_no') in shotids if phase=='within' else bool(c.get('handoff_ref')))]
                    if len(matching)!=1:errors.append(f'{sid} {phase} {entity} 状态变化缺少唯一原因及镜头/交接引用')
        prev=out;prev_sid=sid
        last=Decimal(0)
        for sh in shots:
            if not isinstance(sh,dict):errors.append(f'{sid} 镜头必须为对象');continue
            try:
                start,end=seconds(sh.get('start')),seconds(sh.get('end'))
                if start!=last or end<=start:errors.append(f'{sid} 时间轴须连续且 end > start')
                last=end
            except ValueError as exc:errors.append(f'{sid} {exc}')
            slices=sh.get('dialogue_slices')
            if not isinstance(slices,list):
                errors.append(f'{sid} 每镜必须显式 dialogue_slices（无对白为空列表）')
            else:
                try:
                    rows=structured({'dialogues':slices,'dialogue_free':not slices})
                    ids={a.get('id'):name for name,a in maps['characters'].items() if isinstance(a,dict) and name in seg.get('cast',[])}
                    if any(row[1] not in ids for row in rows):errors.append(f'{sid} 台词说话人未在本段 cast')
                    if any(row[1] in ids and row[2]!=maps['characters'][ids[row[1]]].get('voice_id') for row in rows):errors.append(f'{sid} 声线 ID 未与角色主档对齐')
                    # Current renderer accepts one whole utterance per shot; split via the segment-map workflow.
                    if len(rows)>1:errors.append(f'{sid} 本编译器暂不支持单镜多条台词；请走分段映射/人工适配，不得擅自切镜')
                    if rows:
                        row=rows[0];name=ids.get(row[1],'')
                        expected=re.fullmatch(r'【'+re.escape(name)+r'（[^）]+）：[“"](.*)[”"]】',sh.get('dialogue',''))
                        if not expected or expected.group(1)!=row[3]:errors.append(f'{sid} 文本台词与 dialogue_slices 不一致')
                    elif sh.get('dialogue')!='无':errors.append(f'{sid} 空台词记录必须对应台词：无')
                except ValueError as exc:errors.append(f'{sid} {exc}')
            for key in ('spec','action','sound','dialogue'):
                if not isinstance(sh.get(key),str) or not sh[key].strip(): errors.append(f'{sid} 镜头缺 {key}（无内容须写无）')
        from sd_core import MODEL_LIMITS
        if last>MODEL_LIMITS.get(locks.get('model'),0):errors.append(f'{sid} 超出项目模型时长策略（不是已核实官方限制）')
    try:
        all_slices=[row for seg in segments for shot in seg.get('shots',[]) for row in shot.get('dialogue_slices',[])]
        structured({'dialogues':all_slices,'dialogue_free':not all_slices})
    except ValueError as exc:
        errors.append(f'跨镜台词 ID/链校验失败：{exc}')
    for name,asset in maps['characters'].items():
        if not isinstance(asset,dict):continue
        for item in (asset.get('char_states') or {}).values():
            if not isinstance(item,dict) or not isinstance(item.get('segments'),list) or not item['segments'] or any(s not in seen for s in item['segments']):
                errors.append(f'{name} char_states 必须指定有效 segments 生效范围')
    return errors


def read_receipt(receipt):
    """Actually read cited repository files and return digests; never assert semantic review."""
    if receipt is None:receipt={}
    if not isinstance(receipt,dict): raise ValueError('receipt 必须为对象')
    result=[]
    for ref in receipt.get('read_refs',[]):
        if not isinstance(ref,str):raise ValueError('read_refs 必须为路径列表')
        path=(SUITE/ref).resolve()
        if not path.is_file() and '/' not in ref:
            matches=list(SUITE.glob('*/references/**/'+ref))
            if len(matches)==1:path=matches[0].resolve()
        if not path.is_relative_to(SUITE) or not path.is_file():raise ValueError(f'未找到唯一仓库引用：{ref}')
        result.append(f'{path.relative_to(SUITE).as_posix()} sha256={hashlib.sha256(path.read_bytes()).hexdigest()}')
    return result

# Malformed nested JSON must fail closed without a traceback in the public CLI.
_validate_state = validate_state

def validate_state(state):
    try:
        return _validate_state(state)
    except (TypeError, AttributeError, KeyError, InvalidOperation) as exc:
        return [f'项目嵌套字段类型不合法：{type(exc).__name__}']


def validate_stage_records(state):
    """Check typed stage artifacts against the existing ledger, never claim visual approval."""
    errors=validate_state(state)
    if errors:return errors
    records=state.get('stage_records',{})
    assets={asset['id']:asset for table in ('characters','scenes','props') for asset in state[table].values()}
    segments={s['seg_id']:s for s in state['segments']}
    for stage in ('P0','P1','P2','P3','P4','P5'):
        rows=records.get(stage) if isinstance(records,dict) else None
        if not isinstance(rows,list) or not rows:
            errors.append(f'CT7 {stage} 缺少非空实体交付记录');continue
        expected={'PROJECT'} if stage in ('P0','P4') else set(assets) if stage in ('P1','P2') else set(segments)
        ids=[row.get('entity_id') for row in rows if isinstance(row,dict)]
        if len(ids)!=len(set(ids)) or set(ids)!=expected:errors.append(f'CT7 {stage} 实体覆盖不完整或重复')
        for row in rows:
            if not isinstance(row,dict) or any(not isinstance(row.get(k),str) or not row[k].strip() for k in ('entity_id','artifact_ref','sha256','summary')):
                errors.append(f'CT7 {stage} 记录缺实体、文件、摘要或内容指纹');continue
            path=(SUITE/row['artifact_ref']).resolve()
            if not path.is_relative_to(SUITE) or not path.is_file():errors.append(f'CT7 {stage} 引用不存在或越出仓库');continue
            content=path.read_bytes()
            if not content.strip() or hashlib.sha256(content).hexdigest()!=row['sha256']:
                errors.append(f'CT7 {stage} 文件为空或内容指纹不匹配');continue
            entity=row['entity_id']
            if entity not in expected:continue
            try:
                if stage=='P4':
                    from compile_feed import compile_project_to_feed
                    if content.decode('utf-8').strip()!=compile_project_to_feed(state).strip():raise ValueError('P4 不是当前台账的实际编译产物')
                    continue
                artifact=json.loads(content)
                if artifact.get('stage_id')!=stage or artifact.get('entity_id')!=entity:raise ValueError('阶段/实体归属不符')
                payload=artifact.get('payload')
                if not isinstance(payload,dict) or not payload:raise ValueError('payload 为空')
                if stage=='P0' and payload.get('locks')!=state['locks']:raise ValueError('锁未对齐')
                if stage=='P1' and payload.get('asset')!=assets[entity]:raise ValueError('资产主档未对齐')
                if stage=='P2':
                    if payload.get('asset_id')!=entity:raise ValueError('资产引用未对齐')
                    fields=('views','appearance','negative_prompt')
                    if any(not isinstance(payload.get(k),list) or not payload[k] or any(not isinstance(x,str) or not x.strip() for x in payload[k]) for k in fields):raise ValueError('资产提示词缺分视图/外观/负向记录')
                if stage=='P3' and payload.get('segment')!=segments[entity]:raise ValueError('分镜实体、时间或状态未对齐')
                if stage=='P5':
                    if any(payload.get(k)!=segments[entity][k] for k in ('entry_state','exit_state','state_changes')):raise ValueError('连续性台账不符')
                    if payload.get('unresolved_conflicts')!=[]:raise ValueError('未明确清零逻辑冲突')
            except (ValueError,TypeError,AttributeError,UnicodeError) as exc:
                errors.append(f'CT7 {stage} {entity}: {exc}')
    return errors
