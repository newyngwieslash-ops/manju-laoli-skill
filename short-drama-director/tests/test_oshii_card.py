"""Oshii core/alias regressions. Numbers are fixtures, never creative defaults."""
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import style_card_loader as loader
from test_style_selection import module
from test_style_audit_20 import style_copy

ENTRIES = ('style-lock-ladder', 'style-lock-recommend')

class OshiiTests(unittest.TestCase):
    def cli(self, entry, *args):
        return subprocess.run([sys.executable, str(ROOT/'scripts'/(entry+'.py')), *args],
                              text=True, capture_output=True, cwd='/tmp', timeout=15)

    def test_both_ids_both_entries_card_and_prompt(self):
        expected = loader.render_selection(68, 'prompt', [2,6], [35,50])
        for entry in ENTRIES:
            for sid in (28,68):
                with self.subTest(entry=entry, sid=sid):
                    result = self.cli(entry, '--select', str(sid), '--format', 'card')
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn('编号 68', result.stdout)
                    self.assertIn('待项目审核', result.stdout)
                    self.assertEqual(re.findall(r'^\| (\d+) \|', result.stdout, re.M), list(map(str,range(1,12))))
                    if sid == 28: self.assertIn('兼容编号 28 → 核心编号 68',result.stdout)
                    result = self.cli(entry, '--select', str(sid), '--format', 'prompt',
                                      '--light-range','2','6','--lens-range','35','50')
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), expected)

    def test_errors_are_closed_for_both_ids_and_entries(self):
        invalid = [[], ['--light-range','2','6'],
                   ['--light-range','6','2','--lens-range','35','50'],
                   ['--light-range','nan','6','--lens-range','35','50'],
                   ['--light-range','2','6','--lens-range','35.5','50'],
                   ['--light-range','2','6','--lens-range','0','50'],
                   ['--light-range','2','6','--lens-range','1e999','1e999']]
        for entry in ENTRIES:
            for sid in (28,68):
                for args in invalid:
                    with self.subTest(entry=entry,sid=sid,args=args):
                        result=self.cli(entry,'--select',str(sid),'--format','prompt',*args)
                        self.assertEqual(result.returncode,2)
                        self.assertEqual(result.stdout,'')
                        self.assertNotIn('Traceback',result.stderr)

    def test_prompt_contract_and_no_director_facts(self):
        prompt=loader.render_selection(68,'prompt',[2,6],[35,50])
        self.assertEqual([len(b.splitlines())-1 for b in prompt.split('\n\n')],[9,3])
        self.assertTrue(all(len(line)<=42 for line in prompt.splitlines()))
        self.assertNotRegex(prompt,r'押井|素子|IMAX|P01|S0[1-7]|fps|冷青|长焦|{{')
        issues,_=module('validate_prompt')._c23_check(prompt,style_source='押井守')
        self.assertFalse(any(i.startswith(('C23a','C23d1','C23d2')) for i in issues),issues)

    def test_alias_targets_one_core_and_unknowns_fail(self):
        self.assertEqual(loader.CARD_ALIASES,{28:68})
        self.assertEqual(loader.load_card(28)[1:],loader.load_card(68)[1:])
        for sid in (27,999,True,'28'):
            with self.assertRaises(ValueError): loader.load_card(sid)

    def test_core_mutations_rejected_through_alias(self):
        for filename,old,new in [
            ('director-param-library.md','| 11 | **针对性禁项**','| 10 | **针对性禁项**'),
            ('style-prefix-blocks.md','{{LENS_RANGE}}','[35mm, 50mm]'),
            ('style-prefix-blocks.md','形体骨相：沿用角色资产，动作受力与身体反馈对应\n','')]:
            with style_copy() as d:
                p=d/filename;text=p.read_text();marker='<!-- style-card:68:start -->' if filename.startswith('director') else '<!-- style-block:68:start -->'
                pos=text.index(marker);self.assertIn(old,text[pos:]);p.write_text(text[:pos]+text[pos:].replace(old,new,1))
                for sid in (28,68):
                    with self.assertRaises(ValueError):loader.load_card(sid)

    def test_source_scope_and_existing_nolan_unchanged(self):
        source=(ROOT.parent/'docs/research/oshii/README.md').read_text()
        for token in ('S01','S02','S03','S04','S05','S06','S07','E01','E05','待项目审核','未确认开放','2018','1995','2008'):
            self.assertIn(token,source)
        # Fixed baseline digest includes both Nolan fenced blocks, with no project values.
        self.assertEqual(hashlib.sha256(loader.load_card(36)[2].encode()).hexdigest(),
                         'eb12ff723502e094e9ae9d0c1b86c6b1f9889c6a7d3ada8a5bc151973b064819')

if __name__ == '__main__': unittest.main()
