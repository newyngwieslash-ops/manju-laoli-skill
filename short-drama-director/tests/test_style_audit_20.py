"""Twenty distinct style-system audits. All fixtures are local and temporary."""
import contextlib
from decimal import localcontext, Inexact, Rounded
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(os.environ.get('STYLE_AUDIT_ROOT', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / 'scripts'))
import style_card_loader as loader
ENTRIES = ('style-lock-ladder', 'style-lock-recommend')
CARD_IDS = [9,10,7,12,6,1,33,39,52,64,65,66,71,72,36]

@contextlib.contextmanager
def style_copy():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        for name in ('director-param-library.md', 'style-prefix-blocks.md'):
            shutil.copyfile(loader.STYLE_DIR / name, directory / name)
        with patch.object(loader, 'STYLE_DIR', directory):
            yield directory


def read_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class StyleAudit20(unittest.TestCase):
    def cli(self, entry, *args, root=None, env=None):
        return subprocess.run([sys.executable, str((root or ROOT) / 'scripts' / (entry+'.py')), *args],
                              text=True, capture_output=True, cwd='/tmp', timeout=15, env=env)

    def assert_error(self, result):
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(result.stdout, '')
        self.assertNotIn('Traceback', result.stderr)

    def test_R01_empty_documents(self):
        for name in ('director-param-library.md', 'style-prefix-blocks.md'):
            with style_copy() as d:
                (d/name).write_text('')
                with self.assertRaises(ValueError):
                    loader.load_card(36)

    def test_R02_api_style_id_types(self):
        for sid in ['36', '.*', True, 36.0, None, -36, 0]:
            with self.subTest(style_id=sid), self.assertRaises(ValueError):
                loader.load_card(sid)

    def test_R03_api_range_container_types(self):
        for values in [26, '26', b'26', {'a':2,'b':6}, iter([2,6]), [True,6]]:
            with self.subTest(values=repr(values)), self.assertRaises(ValueError):
                loader.render_selection(36, 'prompt', values, [35,50])

    def test_R04_template_placeholder_integrity(self):
        for replacement in ['[1:2, 1:6]', '{{LENS_RANGE}}']:
            with style_copy() as d:
                p=d/'style-prefix-blocks.md'
                p.write_text(p.read_text().replace('{{LIGHT_RANGE}}',replacement))
                with self.assertRaises(ValueError):
                    loader.render_selection(36,'prompt',[2,6],[35,50])

    def test_R05_duplicate_sections(self):
        for name in ('director-param-library.md', 'style-prefix-blocks.md'):
            with style_copy() as d:
                p=d/name
                text=p.read_text(); target=next(s for s in re.split(r'(?m)(?=^## )',text) if '编号 36' in s.splitlines()[0])
                p.write_text(text+'\n'+target)
                with self.assertRaises(ValueError): loader.load_card(36)

    def test_R06_slot_deletion_and_duplication(self):
        for duplicate in (False,True):
            with style_copy() as d:
                p=d/'director-param-library.md';text=p.read_text();pos=text.index('<!-- style-card:36:start -->')
                tail=text[pos:];row=next(l for l in tail.splitlines() if l.startswith('| 5 |'))
                p.write_text(text[:pos]+tail.replace(row,row+'\n'+row if duplicate else ''))
                with self.assertRaises(ValueError): loader.load_card(36)

    def test_R07_fenced_block_count_and_order(self):
        for mutation in ('extra','reverse'):
            with style_copy() as d:
                p=d/'style-prefix-blocks.md';text=p.read_text();pos=text.index('<!-- style-block:36:start -->');tail=text[pos:]
                if mutation=='extra': tail+='\n```text\nextra\n```\n'
                else:
                    blocks=re.findall(r'```text\n.*?\n```',tail,re.S)
                    tail=tail.replace(blocks[0],'PLACEHOLDER').replace(blocks[1],blocks[0]).replace('PLACEHOLDER',blocks[1])
                p.write_text(text[:pos]+tail)
                with self.assertRaises(ValueError): loader.load_card(36)

    def copied_cli(self, mutate):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'skill';shutil.copytree(ROOT/'scripts',root/'scripts',ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(loader.STYLE_DIR,root/'references/style-bible')
            mutate(root/'references/style-bible/director-param-library.md')
            for entry in ENTRIES: self.assert_error(self.cli(entry,'--select','36',root=root))

    def test_R08_missing_source_cli(self):
        self.copied_cli(lambda p:p.unlink())

    def test_R09_invalid_utf8_cli(self):
        self.copied_cli(lambda p:p.write_bytes(b'\xff\xfe\xff'))

    def test_R10_bom_crlf_compatibility(self):
        expected=loader.render_selection(36,'prompt',[2,6],[35,50])
        with style_copy() as d:
            for p in d.iterdir(): p.write_bytes(b'\xef\xbb\xbf'+p.read_bytes().replace(b'\n',b'\r\n'))
            self.assertEqual(loader.render_selection(36,'prompt',[2,6],[35,50]),expected)

    def test_R11_unicode_space_paths(self):
        with tempfile.TemporaryDirectory(prefix='风格 测试 ') as d:
            root=Path(d)/'技能 副本';shutil.copytree(ROOT/'scripts',root/'scripts',ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(loader.STYLE_DIR,root/'references/style-bible')
            for entry in ENTRIES:
                actual=self.cli(entry,'--select','9','--format','prompt',root=root)
                self.assertEqual(actual.returncode,0,actual.stderr)
                self.assertEqual(actual.stdout,self.cli(entry,'--select','9','--format','prompt').stdout)

    def test_R12_symlink_entrypoints(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'scripts').mkdir()
            for entry in ENTRIES:
                (root/'scripts'/(entry+'.py')).symlink_to(ROOT/'scripts'/(entry+'.py'))
                result=self.cli(entry,'--select','36',root=root)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIn('| 11 |',result.stdout)

    def test_R13_argument_conflicts(self):
        for entry in ENTRIES:
            for args in [('--select','36','--genre','科幻'),('--genre','科幻','--format','prompt'),
                         ('--select','9','--format','prompt','--light-range','2','6'),
                         ('--select','36','--unknown-option'),('--format','prompt')]:
                self.assert_error(self.cli(entry,*args))
            self.assertEqual(self.cli(entry,'--help').returncode,0)

    def test_R14_equivalent_numeric_spellings(self):
        expected=loader.render_selection(36,'prompt',[2,6],[35,50])
        for light,lens in [(['2e0','6.00'],['3.5e1','050']),(['+2','0006'],['35.000','5e1'])]:
            self.assertEqual(loader.render_selection(36,'prompt',light,lens),expected)

    def test_R15_decimal_context_independence(self):
        expected=loader.render_selection(36,'prompt',['2.5','6.25'],[35,50])
        with localcontext() as ctx:
            ctx.prec=1;ctx.traps[Inexact]=True;ctx.traps[Rounded]=True
            self.assertEqual(loader.render_selection(36,'prompt',['2.5','6.25'],[35,50]),expected)

    def test_R16_output_width_boundary(self):
        accepted=rejected=0
        for digits in range(1,19):
            value='9'*digits
            try:
                prompt=loader.render_selection(36,'prompt',[2,6],[value,value])
            except ValueError: rejected+=1
            else:
                accepted+=1
                self.assertTrue(all(len(line)<=42 for line in prompt.splitlines()))
                self.assertIn(value+'mm',prompt)
        self.assertGreater(accepted,0);self.assertGreater(rejected,0)

    def test_R17_cli_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'skill';shutil.copytree(ROOT/'scripts',root/'scripts',ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(loader.STYLE_DIR,root/'references/style-bible')
            def digest(): return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
            before=digest();env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
            for entry in ENTRIES:
                self.assertEqual(self.cli(entry,'--select','36',root=root,env=env).returncode,0)
                self.assert_error(self.cli(entry,'--select','999',root=root,env=env))
            self.assertEqual(digest(),before)

    def test_R18_every_registered_style_loadability(self):
        for entry in ENTRIES:
            rows=read_module(entry).STYLES
            for row in rows:
                if row[0] in CARD_IDS:
                    card,block,prompt=loader.load_card(row[0]);self.assertIn('【STYLE｜',prompt)
                else:
                    with self.assertRaises(ValueError): loader.load_card(row[0])
        self.assertEqual(len(CARD_IDS),15)

    def test_R19_research_is_not_prompt_input(self):
        expected=loader.render_selection(36,'prompt',[2,6],[35,50])
        self.assertNotRegex(expected,r'P01|IMAX|CN-|12 秒|诺兰|Keighley')
        with style_copy() as d:
            # Metadata outside code fences is never part of the delivery payload.
            p=d/'director-param-library.md';p.write_text(p.read_text()+'\nP01 OPTIONAL; CN-IMAX-F01 pending\n')
            self.assertEqual(loader.render_selection(36,'prompt',[2,6],[35,50]),expected)

    def test_R20_c23_boundaries(self):
        validator=read_module('validate_prompt')
        for lo,hi in [(24,85),(35,50),(50,50)]:
            prompt=loader.render_selection(36,'prompt',[2,6],[lo,hi])
            for value in [lo,hi]:
                issues,_=validator._c23_check(prompt+f'\n0s-4s 【镜头1】 镜头 {value}mm，光比 1:2',style_source='诺兰')
                self.assertFalse(any(i.startswith(('C23a','C23b','C23d')) for i in issues),issues)
            issues,_=validator._c23_check(prompt+f'\n0s-4s 【镜头1】 镜头 {hi+1}mm，光比 1:7')
            self.assertGreaterEqual(sum(i.startswith('C23b') for i in issues),2)

if __name__=='__main__': unittest.main()
