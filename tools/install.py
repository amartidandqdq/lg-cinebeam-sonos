"""Install code and unit without starting a service or touching an existing key/config."""
import argparse
import pathlib
import shutil
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]


def install(home):
    home = pathlib.Path(home).resolve()
    target = home / 'sonos-watcher'
    units = home / '.config/systemd/user'
    target.mkdir(parents=True, exist_ok=True)
    units.mkdir(parents=True, exist_ok=True)
    backup = target / ('backup-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    for source, destination in ((ROOT/'watcher/sonos-watcher.py', target/'sonos-watcher.py'),
                                (ROOT/'watcher/sonos-watcher.service', units/'sonos-watcher.service'),
                                (ROOT/'tools/pair.py', target/'pair.py')):
        if destination.exists():
            backup.mkdir(exist_ok=True)
            shutil.copy2(destination, backup/destination.name)
        shutil.copy2(source, destination)
    config = target/'watcher.env'
    if not config.exists():
        shutil.copy2(ROOT/'watcher/watcher.env.example', config)
        config.chmod(0o600)
    (target/'VERSION').write_text((ROOT/'VERSION').read_text())
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=pathlib.Path, default=pathlib.Path.home())
    args = parser.parse_args()
    print('Installed code only at', install(args.home))
    print('Configure watcher.env, pair, then enable the service as documented.')
