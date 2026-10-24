"""Offline contracts, not rendered-image or video acceptance."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1];SUITE=ROOT.parent
sys.path.insert(0,str(ROOT/'scripts'))
from compile_feed import compile_project_to_feed
from project_contract import validate_state,read_receipt,validate_stage_records
import sd_core
spec=importlib.util.spec_from_file_location('dialogue_diff',SUITE/'sd-feed-engine/scripts/script_feed_diff.py');dlg=importlib.util.module_from_spec(spec);spec.loader.exec_module(dlg)
FIX=ROOT/'tests/fixtures/offline'
def fixture(name='two_person'):
    return json.loads((FIX/f'{name}-state.json').read_text(encoding='utf-8'))

class PipelineTests(unittest.TestCase):
    def test_fixed_samples_and_real_cli(self):
        for kind in ('two_person','prop_action','multi_segment'):
            state=fixture(kind);self.assertEqual(validate_state(state),[])
            text=compile_project_to_feed(state);self.assertIn('【时间轴分镜】',text)
            result=subprocess.run([sys.executable,str(ROOT/'scripts/compile_feed.py'),'--state',str(FIX/f'{kind}-state.json')],capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([sys.executable,str(SUITE/'sd-feed-engine/scripts/script_feed_diff.py'),'--script',str(FIX/f'{kind}-script.json'),'--storyboard',str(FIX/f'{kind}-storyboard.json'),'--feed',str(FIX/f'{kind}-feed-dialogues.json')],capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stderr)
    def test_vertical_fractional_and_scope(self):
        state=fixture();text=compile_project_to_feed(state)
        self.assertIn('9:16 竖屏',text);self.assertNotIn('横屏',text);self.assertIn('00:03.5-00:07.5',text)
        self.assertNotIn('@PRP-旧怀表',text)
        state=fixture('multi_segment');text=compile_project_to_feed(state)
        first,second=text.split('## 【投喂单元 2/2')
        self.assertNotIn('@小周',first);self.assertIn('@小周',second)
        self.assertIn('资产状态偏离声明',first);self.assertNotIn('资产状态偏离声明',second)
    def test_required_locks_and_shapes(self):
        for mutate in [lambda s:s['locks'].pop('aspect'),lambda s:s['locks'].update(confirmed=False),lambda s:s['segments'][0].pop('cast'),lambda s:s['segments'][0]['shots'][0].update(start=True),lambda s:s['segments'][0].update(cast=4),lambda s:s['segments'][0]['shots'][0].update(end='nan')]:
            state=fixture();mutate(state)
            with self.assertRaises(ValueError):compile_project_to_feed(state)
        with self.assertRaises(ValueError):compile_project_to_feed(sd_core.default_project_state())
    def test_continuity_and_asset_claims(self):
        state=fixture('multi_segment');state['segments'][1]['entry_state']['旧怀表']['hand']='右手'
        self.assertTrue(validate_state(state))
        for status in ({'generated':True,'inspected':True},{'approved':True},{'accessible':True,'inspected':True}):
            state=fixture();state['characters']['林风']['asset_status']=status;self.assertTrue(validate_state(state))
        state=fixture();state['characters']['林风']['asset_status']={'generated':True,'accessible':False,'inspected':False,'approved':False}
        self.assertEqual(validate_state(state),[])  # M1 without returned image is legitimate.
    def test_receipt_and_model_route(self):
        state=fixture();state.pop('receipt');text=compile_project_to_feed(state)
        self.assertIn('未提供读取记录',text);self.assertNotIn('【默认镜头策略】',text)
        with self.assertRaises(ValueError):read_receipt({'read_refs':['../secret']})
        self.assertIn('sha256=',read_receipt({'read_refs':['short-drama-director/SKILL.md']})[0])
        state=fixture();state['locks']['model']='h3'
        with self.assertRaisesRegex(ValueError,'H3'):compile_project_to_feed(state)
    def test_stage_keywords_do_not_prove_delivery(self):
        self.assertTrue(any('CT7' in x for x in validate_stage_records(fixture())))
    def test_dialogue_negative_mutations(self):
        data=json.loads((FIX/'two_person-script.json').read_text(encoding='utf-8'));before=dlg.structured(data)
        for mutate in (lambda x:x.reverse(),lambda x:x.pop(),lambda x:x.append(x[0]),lambda x:x.__setitem__(0,('D1','WRONG','V1',x[0][3])),lambda x:x.__setitem__(0,('D1','CHR-01','V1','改词'))):
            after=copy.deepcopy(before);mutate(after)
            with self.assertRaises(ValueError):dlg.compare(before,after)
        with self.assertRaises(ValueError):dlg.structured({'dialogues':[]})
        self.assertEqual(dlg.structured({'dialogues':[],'dialogue_free':True}),[])
    def test_dialogue_split_and_approved_edit(self):
        row={'dialogue_id':'D1','speaker_id':'甲','voice_id':'V1','exact_text':'你好','integrity':'CLAUSE_HEAD'}
        tail=dict(row,exact_text='。',integrity='CLAUSE_TAIL')
        self.assertEqual(dlg.structured({'dialogues':[row,tail]})[0][-1],'你好。')
        with self.assertRaises(ValueError):dlg.structured({'dialogues':[row,dict(tail,speaker_id='乙')]})
        before=[('D1','甲','V1','你好。')]
        record={'phase':'script-to-storyboard','dialogue_id':'D1','speaker_id':'甲','before':'你好。','after':None,'status':'approved','approval_ref':'synthetic-test-only','reason':'合成删除负载'}
        dlg.compare(before,[],[record]);record.pop('approval_ref')
        with self.assertRaises(ValueError):dlg.compare(before,[],[record])
