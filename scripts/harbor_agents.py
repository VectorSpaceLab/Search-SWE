"""Harbor agents that require the task image's pinned, preinstalled CLIs."""

from harbor.agents.installed.codex import Codex
from harbor.agents.installed.claude_code import ClaudeCode
from harbor.agents.installed.pi import Pi
from harbor.environments.base import BaseEnvironment
import json
import tempfile
from pathlib import Path

from harbor.models.trajectories.trajectory import Trajectory
from scripts.pi_trajectory import convert_events


CODEX_VERSION = "0.157.1"
CLAUDE_CODE_VERSION = "2.1.283"
PI_VERSION = "0.87.1"


async def _require_version(
    environment: BaseEnvironment,
    *,
    command: str,
    expected: str,
    parse,
    name: str,
) -> None:
    result = await environment.exec(command=command)
    actual = parse(result.stdout or "") if result.return_code == 0 else ""
    if actual != expected:
        raise RuntimeError(
            f"Task image must provide {name} {expected}; found {actual or 'no usable CLI'}"
        )


class PreinstalledCodex(Codex):
    """Run the pinned Codex CLI without runtime package downloads."""

    async def install(self, environment: BaseEnvironment) -> None:
        if self._version != CODEX_VERSION:
            raise RuntimeError(f"Search-SWE requires Codex {CODEX_VERSION}")
        await _require_version(
            environment,
            command=self._INSTALL_VERSION_COMMAND,
            expected=CODEX_VERSION,
            parse=self.parse_version,
            name="Codex",
        )


class PreinstalledClaudeCode(ClaudeCode):
    """Run the pinned Claude Code CLI without runtime package downloads."""

    async def install(self, environment: BaseEnvironment) -> None:
        if self._version != CLAUDE_CODE_VERSION:
            raise RuntimeError(
                f"Search-SWE requires Claude Code {CLAUDE_CODE_VERSION}"
            )
        await _require_version(
            environment,
            command=self._INSTALL_VERSION_COMMAND,
            expected=CLAUDE_CODE_VERSION,
            parse=self.parse_version,
            name="Claude Code",
        )


class PreinstalledPi(Pi):
    """Run the pinned Pi CLI without runtime package downloads."""

    async def run(self, instruction, environment, context):
        try:
            await super().run(instruction, environment, context)
        finally:
            # Export inside the agent phase, before Harbor collects artifacts
            # and provisions the separate verifier. Preserve failed runs too.
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "pi.txt"
                await environment.download_file("/logs/agent/pi.txt", output)
                trajectory, error = convert_events(
                    output.read_text(), instruction, self.model_name, PI_VERSION
                )
                validated = Trajectory.model_validate(trajectory)
                await self._upload_config_text(
                    environment,
                    content=json.dumps(validated.to_json_dict(), ensure_ascii=False),
                    remote_path="/logs/agent/trajectory.json",
                    filename="trajectory.json",
                )
        if error:
            raise RuntimeError(f"Pi execution failed: {error}")

    async def install(self, environment: BaseEnvironment) -> None:
        if self._version != PI_VERSION:
            raise RuntimeError(f"Search-SWE requires Pi {PI_VERSION}")
        await _require_version(
            environment,
            command="pi --version",
            expected=PI_VERSION,
            parse=self.parse_version,
            name="Pi",
        )
