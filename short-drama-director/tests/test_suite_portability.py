"""Discover/install-copy smoke test, not third-party host certification."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'short-drama-director/scripts'))
import model_contract

class PortabilityTests(unittest.TestCase):
    def test_thirteen_sibling_skills_discover_and_run(self):
        skills=[ROOT/'short-drama-director',*sorted(ROOT.glob('sd-*-engine'))]
        self.assertEqual(len(skills),13)
        with tempfile.TemporaryDirectory(prefix='技能 suite ') as d:
            dest=Path(d)
            for skill in skills:
                self.assertTrue((skill/'SKILL.md').is_file())
                shutil.copytree(skill,dest/skill.name,ignore=shutil.ignore_patterns('__pycache__'))
            script=dest/'short-drama-director/scripts/style-lock-ladder.py'
            result=subprocess.run([sys.executable,'-X','utf8',str(script),'--select','28'],cwd=dest,text=True,encoding='utf-8',capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('核心编号 68',result.stdout)
    def test_model_policy_is_single_source_and_uncertified(self):
        self.assertEqual(model_contract.sync(),[])
        for profile in model_contract.PROFILES.values():
            self.assertIsNone(profile['official_limits'])
            for key in ('provider','model','task_mode','source','checked_at','evidence_status'):
                self.assertTrue(profile[key])

    def test_gate_uses_model_specific_budget(self):
        from test_pipeline_contract import fixture
        from compile_feed import compile_project_to_feed
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'feed.md'
            text=compile_project_to_feed(fixture())
            # 2100 chars added guarantees 2.0 is over hard budget; compare the emitted thresholds.
            text=text.replace('【音效】','【音效】'+'测试'*1600)
            path.write_text(text,encoding='utf-8')
            for model,limit in (('2.0',2000),('2.5',3000)):
                result=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'sd-feed-engine/scripts/gate_check.py'),str(path),'--model',model],capture_output=True,text=True,encoding='utf-8')
                self.assertIn(f'> {limit}（model={model}',result.stdout)
