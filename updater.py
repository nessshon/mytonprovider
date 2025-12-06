#!/usr/bin/env python3
# -*- coding: utf_8 -*-

import time
import traceback

from mypylib import MyPyClass
from utils import (
	import_modules,
	get_module_by_name
)

INTERVAL = 10 * 60

if __name__ == "__main__":
	local = MyPyClass(__file__)
	#local.run()
	import_modules(local)
	auto_updater_module = get_module_by_name(local, "auto-updater")

	while True:
		try:
			auto_updater_module.update_modules()
		except Exception as e:
			local.add_log(f"[auto-updater] error: {e!r}")
			tb = traceback.format_exc()
			local.add_log(f"[auto-updater] traceback:\n{tb}")

		local.add_log(f"[auto-updater] sleep {INTERVAL} seconds")
		time.sleep(INTERVAL)
#end if
