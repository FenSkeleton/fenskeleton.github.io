# -*- coding: utf-8 -*-
import os
import sys

# FenSkeleton Android/Kodi safety: skin buttons can invoke this file without a
# normal plugin context. Keep the addon lib and addon root on sys.path so
# imports such as modules.*, service and resources.lib.* resolve consistently.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ADDON_ROOT = os.path.abspath(os.path.join(_THIS_DIR, os.pardir, os.pardir))
for _path in (_THIS_DIR, _ADDON_ROOT):
	if _path not in sys.path:
		sys.path.insert(0, _path)

from modules.router import routing, sys_exit_check

routing(sys)
if sys_exit_check(): sys.exit(1)
