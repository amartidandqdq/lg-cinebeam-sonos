import pathlib
import shutil
import subprocess

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "restore-root.sh"


@pytest.mark.skipif(shutil.which("sh") is None, reason="needs a POSIX sh")
def test_restore_removes_only_marked_hosts_lines(tmp_path):
    hosts = tmp_path / "hosts"
    hosts.write_text("127.0.0.1 localhost\n"
                     "127.0.0.1 ads.example # lg-debloat\n"
                     "::1 ads.example # lg-debloat\n"
                     "10.0.0.5 nas\n")
    subprocess.run(["sh", str(SCRIPT)], env={"PATH": "/usr/bin:/bin", "HOSTS_FILE": str(hosts)}, check=True)
    assert hosts.read_text() == "127.0.0.1 localhost\n10.0.0.5 nas\n"
