"""Fresh-process transport. Input is explicit JSON; no labels are sent.

Purpose: prove persistence and invocation boundaries instead of simulating reset
with an in-process method. `restore` sees a ledger artifact; `propose` sees only
the rendered context argument. This is data-flow isolation, NOT an OS sandbox.
Failure: errors exit nonzero and parent `subprocess.run(check=True)` fails loudly.
Evidence: test_subprocess_roundtrip_and_replay.
"""

import json
import importlib.util
import os
from pathlib import Path
import sys

# Load only this package explicitly; do not add its root ahead of the stdlib or
# accidentally choose a globally installed package with the same name. This is
# still trusted code, not an OS sandbox. Evidence: test_worker_root_cannot_shadow_stdlib.
package_directory = Path(__file__).resolve().parent
package_spec = importlib.util.spec_from_file_location('continuity', package_directory / '__init__.py',
                                                     submodule_search_locations=[str(package_directory)])
package_module = importlib.util.module_from_spec(package_spec)
sys.modules['continuity'] = package_module
package_spec.loader.exec_module(package_module)
from continuity.core import propose, render_memory  # noqa: E402
from continuity.storage import restore  # noqa: E402


def main() -> None:
    request = json.load(sys.stdin)
    # Reject undeclared evaluator metadata instead of silently ignoring a label.
    # Evidence: test_worker_rejects_label_fields.
    expected = ({'operation', 'directory', 'manifest', 'task_id', 'strategy', 'budget'}
                if request.get('operation') == 'restore' else {'operation', 'context'})
    if set(request) != expected:
        raise ValueError('worker input fields do not match declared operation')
    if request["operation"] == "restore":
        events = restore(Path(request["directory"]), request["manifest"])
        value = render_memory(events, request["task_id"], request["strategy"], request["budget"])
    elif request["operation"] == "propose":
        value = propose(request["context"])
    else:
        raise ValueError("unknown worker operation")
    print(json.dumps({"pid": os.getpid(), "value": value}, ensure_ascii=True, allow_nan=False))


if __name__ == "__main__":
    main()
