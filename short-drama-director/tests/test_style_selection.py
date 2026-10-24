import tempfile
"""CLI and content regressions; numeric fixtures are test inputs, not defaults."""
import contextlib
import importlib.util
import io
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from style_card_loader import load_card, render_selection


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SelectionTests(unittest.TestCase):
    def cli(self, entry, *args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts' / (entry + '.py')), *args],
                              text=True, capture_output=True, cwd=tempfile.gettempdir(), encoding='utf-8')

    def test_both_entrypoints_full_card_and_prompt(self):
        for entry in ('style-lock-ladder', 'style-lock-recommend'):
            with self.subTest(entry=entry):
                result = self.cli(entry, '--select', '36')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('| 11 | **针对性禁项**', result.stdout)
                self.assertIn('仍待审', result.stdout)
                self.assertIn('默认不注入', result.stdout)
                result = self.cli(entry, '--select', '36', '--format', 'prompt',
                                  '--light-range', '2', '6', '--lens-range', '35', '50')
                self.assertEqual(result.returncode, 0, result.stderr)
                prompt = result.stdout
                self.assertIn('光比 [1:2, 1:6]', prompt)
                self.assertIn('镜头 [35mm, 50mm]', prompt)
                self.assertNotRegex(prompt, r'IMAX|P01|CN-|诺兰|65mm|Keighley|冷蓝|fps|12 秒')
                blocks = prompt.strip().split('\n\n')
                self.assertEqual([len(b.splitlines()) - 1 for b in blocks], [9, 3])
                self.assertTrue(all(len(line) <= 42 for b in blocks for line in b.splitlines()[1:-1]))

    def test_unknown_values_fail_closed(self):
        for entry in ('style-lock-ladder', 'style-lock-recommend'):
            for args in [('--select', '36', '--format', 'prompt'),
                         ('--select', '999'),
                         ('--select', '36', '--format', 'prompt', '--light-range', '2', '6', '--lens-range', '35.5', '50'),
                         ('--select', '36', '--format', 'prompt', '--light-range', '6', '2', '--lens-range', '35', '50'),
                         ('--select', '36', '--format', 'prompt', '--light-range', 'nan', '6', '--lens-range', '35', '50')]:
                result = self.cli(entry, *args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')

    def test_registry_counts_and_selection(self):
        ladder, rec = module('style-lock-ladder'), module('style-lock-recommend')
        a, b = {s[0] for s in ladder.STYLES}, {s[0] for s in rec.STYLES}
        self.assertEqual((len(a), len(b), len(a | b)), (48, 44, 55))
        self.assertIn('诺兰向', ladder.recommend('真人 科幻 巨物 结构 战争'))
        self.assertIn(36, [s[0] for s in rec.recommend('战争 史诗')[3]])
        self.assertIn('--select 36', ladder.recommend('真人 科幻 巨物 结构 战争'))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rec.render('战争 史诗')
        self.assertIn('--select 36', output.getvalue())
        # Existing route and exclusion behavior remain intact.
        self.assertEqual(rec.recommend('都市情感夜戏，无打斗')[3][0][0], 10)
        self.assertNotIn(10, [s[0] for s in rec.recommend('玄幻仙侠打斗，有法术特效')[3]])
        self.assertIn('王家卫向', ladder.recommend('都市情感夜戏，无打斗'))
        for entry in ('style-lock-ladder', 'style-lock-recommend'):
            self.assertEqual(self.cli(entry).returncode, 0)
            self.assertEqual(self.cli(entry, '--genre', '战争 史诗').returncode, 0)
            self.assertEqual(self.cli(entry, '--select', '9', '--format', 'prompt').returncode, 0)

    def test_sixteen_core_cards_and_existing_blocks(self):
        ids = [9, 10, 7, 12, 6, 1, 33, 39, 52, 64, 65, 66, 71, 72, 36, 68]
        for style_id in ids:
            card, block, prompt = load_card(style_id)
            self.assertIn('【STYLE', prompt)
            self.assertIn('【PERFORMANCE', prompt)
        text = (ROOT / 'references/style-bible/director-param-library.md').read_text(encoding='utf-8')
        rows = re.findall(r'^\|\s*\*\*(\d+) [^|]+\|\s*T\d\s', text, re.M)
        self.assertEqual(set(map(int, rows)), set(ids))
        self.assertEqual(len(rows), 16)
        catalog = (ROOT / 'references/style-bible/director-style-catalog-74.md').read_text(encoding='utf-8')
        self.assertEqual(len(re.findall(r'^\| \d+ \| \*\*', catalog, re.M)), 74)

    def test_c23_validation_and_range_guard(self):
        validator = module('validate_prompt')
        prompt = render_selection(36, 'prompt', [2, 6], [35, 50])
        issues, _ = validator._c23_check(prompt, style_source='诺兰')
        self.assertFalse(any(i.startswith(('C23a', 'C23d1', 'C23d2')) for i in issues), issues)
        issues, _ = validator._c23_check(prompt + '\n0s-4s 【镜头1】 镜头 85mm，光比 1:9')
        self.assertTrue(any(i.startswith('C23b') for i in issues), issues)


if __name__ == '__main__':
    unittest.main()
