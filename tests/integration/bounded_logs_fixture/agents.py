"""Real Harbor run/conversion methods with offline executable fixtures."""
from harbor.agents.installed.antigravity_cli import AntigravityCli
from harbor.agents.installed.gemini_cli import GeminiCli
from harbor.agents.installed.pi import Pi
from scripts.evaluation.harbor_agents import ManagedCodex, ManagedClaudeCode, ManagedPi
from scripts.evaluation.native_agents import NativeLifecycle
from scripts.evaluation.pi_trajectory import PiTrajectory
from scripts.evaluation.antigravity_trajectory import AntigravityTrajectory
from scripts.evaluation.bounded_logs import FinalizeBoundedLogs


class FixtureSetup:
    async def setup(self, environment):
        result = await environment.exec('/opt/conda/bin/python /task/quota_probe.py')
        assert result.return_code == 0, (result.return_code, result.stdout, result.stderr)
        result = await environment.exec('mkdir -p "$HOME/.local/bin" && ln -sf /usr/local/bin/agy "$HOME/.local/bin/agy"')
        assert result.return_code == 0, (result.return_code, result.stdout, result.stderr)
        (self.logs_dir / 'harness.json').write_text('{"source":"trusted fixture metadata"}')


class Codex(FixtureSetup, ManagedCodex):
    pass


class Claude(FixtureSetup, ManagedClaudeCode):
    pass


class IntegratedPi(FixtureSetup, ManagedPi):
    pass


class NativePi(FixtureSetup, FinalizeBoundedLogs, NativeLifecycle, PiTrajectory, Pi):
    HARNESS_NAME = 'pi'


class Gemini(FixtureSetup, FinalizeBoundedLogs, NativeLifecycle, GeminiCli):
    HARNESS_NAME = 'gemini-cli'


class Antigravity(FixtureSetup, FinalizeBoundedLogs, NativeLifecycle, AntigravityTrajectory, AntigravityCli):
    HARNESS_NAME = 'antigravity-cli'
