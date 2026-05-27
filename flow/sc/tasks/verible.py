"""Verible lint task for SiliconCompiler flows."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from siliconcompiler import Task


class VeribleLintTask(Task):
    """Run verible-verilog-lint and record lint messages as warnings."""

    def __init__(self):
        super().__init__()
        self.add_parameter("sources", "[file]", "Verilog/SystemVerilog files to lint")

    def tool(self):
        return "frida"

    def task(self):
        return "verible_lint"

    def add_source(self, source: str | Path) -> None:
        self.add("var", "sources", str(source))

    def setup(self):
        super().setup()
        self.add_output_file("verible_lint.log")
        self.add_required_key("var", "sources")

    def run(self):
        outputs = Path("outputs")
        outputs.mkdir(exist_ok=True)
        log_path = outputs / "verible_lint.log"

        cmd = ["verible-verilog-lint", *self.find_files("var", "sources")]
        proc = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        log_path.write_text(proc.stdout)

        lint_messages = [line for line in proc.stdout.splitlines() if re.match(r"^.*:\d+:\d+", line)]
        hard_errors = [
            line for line in proc.stdout.splitlines() if "syntax error" in line.lower() or line.startswith("ERROR:")
        ]

        self.record_metric("warnings", len(lint_messages), source_file=log_path)
        self.record_metric("errors", len(hard_errors), source_file=log_path)
        return 0 if not hard_errors else proc.returncode
