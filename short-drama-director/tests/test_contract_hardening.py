"""Negative regressions for explicit card selection and contract scope."""
import contextlib
import io
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import audit_contract as audit
import style_card_loader as loader

class ContractTests(unittest.TestCase):
    def test_shared_ids_aliases_and_names(self):
        for value,sid in [('王家卫',10),('徐克',9),('36',36),('68',68),('28',28)]:
            self.assertEqual(audit.resolve_director(value)[0],sid)
        for value in (None,'999','03','04','未知'):
            with self.assertRaises(ValueError):audit.resolve_director(value)
    def test_missing_unknown_incomplete_or_keywords_fail(self):
        for value in (None,'999','27','36'):
            self.assertTrue(any(x.startswith('CT3-STY') for x in audit.audit_markdown('冷青 对称 STYLE PERFORMANCE',director=value)[0]))
    def test_real_blocks_and_alias_compatible(self):
        for sid in (9,10,36,28,68):
            prompt=loader.render_selection(sid,'prompt',*(([2,6],[35,50]) if sid in (36,28,68) else (None,None)))
            self.assertIsNone(audit.check_style(prompt,sid))
            self.assertIsNotNone(audit.check_style(prompt.replace('成像底层：','伪造：'),sid))
    def test_init_command(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out):audit.print_init_checklist(director='28')
        self.assertIn('--select 28',out.getvalue());self.assertNotIn('--card ',out.getvalue())

    def test_invalid_ranges_rejected(self):
        prompt=loader.render_selection(68,'prompt',[2,6],[35,50])
        for broken in (prompt.replace('[1:2, 1:6]','[1:0, 1:0]'),prompt.replace('[35mm, 50mm]','[99mm, 1mm]')):
            self.assertIsNotNone(audit.check_style(broken,68))
