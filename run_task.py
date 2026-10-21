"""Run a module in the background with its output appended to a log file, for the Windows scheduled tasks.

Started with pythonw.exe (no console window), e.g.:
    pythonw.exe run_task.py arb_scanner data\\lines\\arb_scanner.log scheduled
    pythonw.exe run_task.py refresh data\\refresh.log

Any program the module starts (git, Docker, PowerShell) is started without a window too.
"""
import os
import runpy
import subprocess
import sys
import traceback

if os.name == "nt":
    _run, _popen_init = subprocess.run, subprocess.Popen.__init__

    def _hidden_popen_init(self, *args, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
        _popen_init(self, *args, **kwargs)
    subprocess.Popen.__init__ = _hidden_popen_init


def main():
    module, log, rest = sys.argv[1], sys.argv[2], sys.argv[3:]
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(os.path.dirname(log) or ".", exist_ok=True)
    with open(log, "a", encoding="utf-8", buffering=1) as f:
        sys.stdout = sys.stderr = f
        sys.argv = [module, *rest]
        try:
            runpy.run_module(module, run_name="__main__", alter_sys=True)
        except SystemExit:
            pass
        except Exception:
            traceback.print_exc()


if __name__ == "__main__":
    main()
