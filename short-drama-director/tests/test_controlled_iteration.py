"""Frozen regression contract; fixture outputs originate at its recorded before_sha."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import style_card_loader as loader

ENTRIES = ('style-lock-ladder', 'style-lock-recommend')


class ControlledIterationTests(unittest.TestCase):
    def cli(self, entry, *args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts' / (entry + '.py')), *args],
                              capture_output=True, text=True, timeout=10, cwd=tempfile.gettempdir(), encoding='utf-8')

    def test_frozen_old_cards_and_recommendations(self):
        fixture = json.loads((ROOT / 'tests/fixtures/style_before.json').read_text(encoding='utf-8'))
        digest = lambda s: hashlib.sha256(s.encode()).hexdigest()
        registries = json.loads((ROOT / 'tests/fixtures/style_registries_before.json').read_text(encoding='utf-8'))['registries']
        for sid, expected in fixture['old_prompts'].items():
            self.assertEqual(digest(loader.load_card(int(sid))[2]), expected, sid)
            for entry in ENTRIES:
                # Not every complete card is registered in both historical entrypoints.
                result = self.cli(entry, '--select', sid, '--format', 'prompt')
                if sid in registries[entry]:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(digest(result.stdout.rstrip('\n')), expected, (entry, sid))
                else:
                    self.assertEqual(result.returncode, 2)
                    self.assertIn('该编号未在此入口注册', result.stderr)
        for case in fixture['recommendations']:
            result = self.cli(case['entry'], '--genre', case['genre'])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(digest(result.stdout), case['sha256'], case)

    def test_missing_and_invalid_ranges(self):
        base = ('--select', '36', '--format', 'prompt')
        invalid = [(), ('--light-range', '2', '6'), ('--lens-range', '35', '50'),
                   ('--light-range', '2'),
                   ('--light-range', '2', '6', '--lens-range', '0', '50'),
                   ('--light-range', '-2', '6', '--lens-range', '35', '50'),
                   ('--light-range', '2', '6', '--lens-range', '50', '35'),
                   ('--light-range', '2.0000000000000001', '2', '--lens-range', '35', '50')]
        for token in ['nan', 'inf', '1e309', '1e-300', '1e999999999', '9007199254740993', 'oops']:
            invalid.append(('--light-range', token, token, '--lens-range', '35', '50'))
            invalid.append(('--light-range', '2', '6', '--lens-range', token, token))
        for entry in ENTRIES:
            for args in invalid:
                with self.subTest(entry=entry, args=args):
                    result = self.cli(entry, *base, *args)
                    self.assertEqual(result.returncode, 2, result.stdout)
                    self.assertEqual(result.stdout, '')
                    self.assertNotIn('Traceback', result.stderr)

    def test_valid_structure_and_exact_values(self):
        for entry in ENTRIES:
            for light, lens in [(('2.5', '6.25'), ('35', '50')), (('2', '2'), ('50', '50'))]:
                result = self.cli(entry, '--select', '36', '--format', 'prompt',
                                  '--light-range', *light, '--lens-range', *lens)
                self.assertEqual(result.returncode, 0, result.stderr)
                blocks = result.stdout.strip().split('\n\n')
                self.assertEqual([len(b.splitlines()) for b in blocks], [10, 4])
                self.assertTrue(blocks[0].startswith('【STYLE｜'))
                self.assertTrue(blocks[1].startswith('【PERFORMANCE｜'))
                for block in blocks:
                    self.assertTrue(all(len(l) <= 42 for l in block.splitlines()[1:]))
                self.assertIn(f'光比 [1:{light[0]}, 1:{light[1]}]', result.stdout)
                self.assertNotRegex(result.stdout, r'\{\{|P01|IMAX|CN-|诺兰|12 秒')

    def test_api_rejects_invalid_shape_and_mode(self):
        for values in ([2], [2, 6, 7], []):
            with self.assertRaises(ValueError):
                loader.render_selection(36, 'prompt', values, [35, 50])
        with self.assertRaises(ValueError):
            loader.render_selection(36, 'unknown', [2, 6], [35, 50])

    def test_malformed_blocks_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d)
            for name in ('director-param-library.md', 'style-prefix-blocks.md'):
                (dest / name).write_text((loader.STYLE_DIR / name).read_text(encoding='utf-8'), encoding='utf-8')
            path = dest / 'style-prefix-blocks.md'
            # Change only the Nolan PERFORMANCE heading, leaving two fenced blocks.
            text = path.read_text(encoding='utf-8'); pos = text.index('<!-- style-block:36:start -->')
            path.write_text(text[:pos] + text[pos:].replace('【PERFORMANCE｜', '【STYLE｜'), encoding='utf-8')
            with patch.object(loader, 'STYLE_DIR', dest), self.assertRaises(ValueError):
                loader.load_card(36)


if __name__ == '__main__':
    unittest.main()
