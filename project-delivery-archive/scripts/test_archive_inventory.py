import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from archive_inventory import compare, inventory


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.source = self.base/'source'
        self.source.mkdir()
        (self.source/'empty').mkdir()
        (self.source/'设计 稿.txt').write_text('synthetic data')
        (self.source/'link').symlink_to('设计 稿.txt')

    def clone(self):
        target = self.base/'archive'
        shutil.copytree(self.source, target, symlinks=True)
        return target

    def test_complete_copy_and_content_change(self):
        target = self.clone()
        a = inventory(self.source, True)
        self.assertTrue(compare(a, inventory(target, True))['match'])
        (target/'设计 稿.txt').write_text('different data')
        self.assertFalse(compare(a, inventory(target, True))['match'])

    def test_metadata_cannot_prove_content(self):
        self.assertFalse(compare(inventory(self.source), inventory(self.clone()))['match'])

    def test_placeholder_blocks_complete(self):
        (self.source/'.draft.icloud').touch()
        m = inventory(self.source, True)
        self.assertFalse(m['content_inventory_complete'])
        self.assertIn('.draft.icloud', m['unresolved_paths'])

    def test_missing_empty_directory_detected(self):
        target = self.clone()
        (target/'empty').rmdir()
        self.assertEqual(compare(inventory(self.source, True), inventory(target, True))['missing'], ['empty'])

    def test_external_symlink_not_followed(self):
        (self.source/'outside').symlink_to(self.base)
        m = inventory(self.source, True)
        self.assertEqual(len([e for e in m['entries'] if e['path'].startswith('outside')]), 1)

    def test_read_failure_blocks_complete(self):
        with patch('archive_inventory.hash_regular', side_effect=OSError('simulated read failure')):
            self.assertFalse(inventory(self.source, True)['content_inventory_complete'])

    def test_directory_swap_cannot_escape_root(self):
        nested = self.source/'nested'
        nested.mkdir()
        outside = self.base/'outside'
        outside.mkdir()
        (outside/'private.txt').write_text('must not be read')
        real_open = os.open
        swapped = False
        def racing_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if path == 'nested' and not swapped:
                swapped = True
                nested.rmdir()
                nested.symlink_to(outside, target_is_directory=True)
            return real_open(path, flags, *args, **kwargs)
        with patch('archive_inventory.os.open', side_effect=racing_open):
            # Preserve platform capability detection when the function is patched.
            with patch('archive_inventory.os.supports_dir_fd', os.supports_dir_fd | {os.open}):
                m = inventory(self.source, True)
        self.assertFalse(m['content_inventory_complete'])
        self.assertFalse(any(e['path'].endswith('private.txt') for e in m['entries']))

    def test_cli_output_safety(self):
        script = Path(__file__).with_name('archive_inventory.py')
        for output in (self.source/'manifest.json', self.base/'existing.json'):
            if output.name == 'existing.json':
                output.write_text('keep')
            result = subprocess.run([sys.executable, str(script), 'scan', str(self.source), '--output', str(output)], capture_output=True)
            self.assertEqual(result.returncode, 2)
        self.assertEqual((self.base/'existing.json').read_text(), 'keep')
        self.assertFalse((self.source/'manifest.json').exists())


if __name__ == '__main__':
    unittest.main()
