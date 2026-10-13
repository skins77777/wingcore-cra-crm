"""Recovery regression checks without touching WSL or customer data."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('local_services', Path(__file__).with_name('start-local-services.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class RecoveryTests(unittest.TestCase):
    def test_foreign_reused_pid_is_not_a_holder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'runtime').mkdir()
            (root / 'runtime/wsl-session.json').write_text('{"ProcessId": 42}')
            with patch.object(module, 'ROOT', root), patch.object(module, 'process_command', return_value='unrelated.exe'), patch.object(module, 'detached', return_value=Mock(pid=99)) as launch:
                self.assertEqual(module.ensure_holder(), 99)
                self.assertIn('sleep', launch.call_args.args[0])

    def test_matching_holder_is_reused(self):
        with patch.object(module, 'read_state', return_value={'ProcessId':42}), patch.object(module, 'process_command', return_value='wsl.exe -d CRA-Ubuntu-24.04 -- sleep infinity'), patch.object(module, 'detached') as launch:
            self.assertEqual(module.ensure_holder(), 42)
            launch.assert_not_called()

    def test_healthy_stack_is_not_restarted(self):
        rows = '\n'.join(json.dumps({'Service':s, 'State':'running', 'Health':'healthy'}) for s in ('server','db'))
        with patch.object(module, 'run', return_value=rows) as command:
            self.assertFalse(module.ensure_stack('twenty', ('server','db'))['recoveryNeeded'])
            self.assertEqual(command.call_count, 1)

    def test_missing_stack_recovers_without_pull_or_build(self):
        with patch.object(module, 'run', side_effect=['','']) as command:
            self.assertTrue(module.ensure_stack('twenty', ('server','db'))['recoveryNeeded'])
            recovery = command.call_args.args[0]
            self.assertIn('--no-build', recovery)
            self.assertEqual(recovery[recovery.index('--pull')+1], 'never')

    def test_ip_change_does_not_reuse_or_launch_proxy(self):
        route = '[{"gateway":"172.22.0.1"}]'
        adapter = '[{"addr_info":[{"family":"inet","local":"172.22.0.2"}]}]'
        with patch.object(module, 'wsl', side_effect=[route,adapter]), patch.object(module, 'read_state', return_value={'Gateway':'old','Client':'old'}), patch.object(module, 'detached') as launch:
            self.assertFalse(module.ensure_proxy()['ok'])
            launch.assert_not_called()

    def test_child_commands_have_no_console(self):
        with patch.object(module.subprocess, 'run', return_value=Mock(returncode=0, stdout='ok')) as command:
            module.run(['example'])
            self.assertEqual(command.call_args.kwargs['creationflags'], module.FLAGS)
        with patch.object(module.subprocess, 'Popen') as launch:
            module.detached(['example'])
            self.assertEqual(launch.call_args.kwargs['creationflags'], module.FLAGS)

    def test_powershell_process_paths_use_utf8(self):
        with patch.object(module, 'run', return_value='K:\\CRA客户项目') as command:
            self.assertEqual(module.powershell('example'), 'K:\\CRA客户项目')
            self.assertIn('OutputEncoding', command.call_args.args[0][-1])

if __name__ == '__main__':
    unittest.main()
