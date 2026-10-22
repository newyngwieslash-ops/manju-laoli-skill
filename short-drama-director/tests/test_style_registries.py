"""Fixed ID/name contracts; expected data is never regenerated during tests."""
import ast
import copy
import json
from pathlib import Path
import runpy
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/style_registries_before.json'


class RegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = json.loads(FIXTURE.read_text(encoding='utf-8'))

    def assert_registry(self, entry, script):
        rows = runpy.run_path(str(script))['STYLES']
        ids = [row[0] for row in rows]
        self.assertEqual(len(ids), len(set(ids)), 'duplicate style ID')
        actual = {str(row[0]): row[1] for row in rows}
        self.assertEqual(actual, self.baseline['registries'][entry], entry)

    def test_fixture_provenance_and_counts(self):
        self.assertEqual(self.baseline['before_sha'],
                         '6a43a17cf866ed664e362696f90d82879a22d92c')
        data = self.baseline['registries']
        self.assertEqual(set(data), {'style-lock-ladder', 'style-lock-recommend'})
        self.assertEqual(len(data['style-lock-ladder']), 48)
        self.assertEqual(len(data['style-lock-recommend']), 44)
        self.assertEqual(len(set(data['style-lock-ladder']) | set(data['style-lock-recommend'])), 55)

    def test_each_entry_matches_fixed_id_name_mapping(self):
        for entry in self.baseline['registries']:
            with self.subTest(entry=entry):
                self.assert_registry(entry, ROOT / 'scripts' / (entry + '.py'))

    def test_temporary_script_mutations_are_rejected(self):
        # Exercise the same checker against actual modified script copies.
        # A no-op copy must pass before its deleted/renamed/added/duplicate variants fail.
        for entry in self.baseline['registries']:
            source = (ROOT / 'scripts' / (entry + '.py')).read_text(encoding='utf-8')
            with tempfile.TemporaryDirectory() as directory:
                script = Path(directory) / (entry + '.py')
                script.write_text(source, encoding='utf-8')
                self.assert_registry(entry, script)
                for mutation in ('delete', 'rename', 'add', 'duplicate'):
                    with self.subTest(entry=entry, mutation=mutation):
                        tree = ast.parse(source)
                        rows = next(n.value.elts for n in tree.body
                                    if isinstance(n, ast.Assign) and any(
                                        isinstance(t, ast.Name) and t.id == 'STYLES' for t in n.targets))
                        if mutation == 'delete':
                            rows.pop(0)
                        elif mutation == 'rename':
                            rows[0].elts[1] = ast.Constant('unexpected renamed style')
                        else:
                            added = copy.deepcopy(rows[0])
                            if mutation == 'add':
                                added.elts[0] = ast.Constant(999)
                            rows.append(added)
                        ast.fix_missing_locations(tree)
                        script.write_text(ast.unparse(tree), encoding='utf-8')
                        with self.assertRaises(AssertionError):
                            self.assert_registry(entry, script)


if __name__ == '__main__':
    unittest.main()
