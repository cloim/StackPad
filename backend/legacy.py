"""Carry data and the login shortcut over from the app's former name, once."""
import os
import shutil
from pathlib import Path

# The only place the former name may appear: folders and files written by earlier versions.
FORMER_NAME = 'ServiceDeck'


def former_data_dirs():
    dirs = [Path.home() / '.config' / FORMER_NAME]
    if os.environ.get('APPDATA'):
        dirs.append(Path(os.environ['APPDATA']) / FORMER_NAME)
    return dirs


def migrate_data(target, sources=None):
    """Copy the first former data folder into an unused target and keep the original. Returns the source or None."""
    target = Path(target)
    if (target / 'config.json').exists() or (target / 'storage-location.json').exists():
        return None
    for source in sources or former_data_dirs():
        if (source / 'config.json').is_file() or (source / 'storage-location.json').is_file():
            # Running services keep writing to their absolute log paths in the former folder until restarted.
            shutil.copytree(source, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns('*.tmp', 'cloudflare-access.json'))
            return source
    return None


def former_startup_link():
    return Path(os.environ['APPDATA']) / f'Microsoft/Windows/Start Menu/Programs/Startup/{FORMER_NAME}.lnk'


def migrate_startup_link(engine):
    """Replace the former login shortcut with one for the current executable."""
    # Only the desktop app knows its own path; other launches leave the former shortcut alone.
    if not engine.desktop_exe or not os.environ.get('APPDATA'):
        return False
    link = former_startup_link()
    if not link.exists():
        return False
    engine.autostart(True)
    link.unlink(missing_ok=True)
    return True
