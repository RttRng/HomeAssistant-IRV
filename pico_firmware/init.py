import json
import os
from machine import WDT
from crash_lib import *



def _debug_flag_present():
    try:
        os.stat("debug.flag")
        print("[DEBUG]")
        return True
    except OSError:
        return False

try:
    from log_lib import Logger
    logger = Logger()
except:
    class Logger:
        def __init__(self) -> None:
            self.wdt = None
        def set_wdt(self,wdt):
            self.wdt = wdt
        def feed(self):
            self.wdt.feed()
        def print(self,*args, end="\n"):
            print(*args, end=end)
    logger = Logger()

DEBUG = _debug_flag_present()
if not DEBUG:
    logger.print("Initializing WDT")
    logger.set_wdt(WDT(timeout=8000))

def run():
    CRASH_THRESHOLD = 3
    MAX_TRACKED_CRASHES = 20
    crash_count = min(read_crash_count(), MAX_TRACKED_CRASHES)
    import rescue
    if crash_count >= CRASH_THRESHOLD:
        print("Crash threshold reached (", crash_count, "), going to rescue")
        rescue.run(logger,reason="crash_threshold")
    else:
        try:
            import primary
            reason, error = "primary_returned", ""
        except Exception as e:
            reason, error = "exception", e
        finally:
            write_crash_count(crash_count + 1)

        print("primary.py ended:", reason, error)
        rescue.run(logger, reason=reason, error=error)