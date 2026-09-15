import json
import os

def _debug_flag_present():
    try:
        os.stat("debug.flag")
        return True
    except OSError:
        return False

DEBUG = _debug_flag_present()
if DEBUG:
    pass
else:
    from log_lib import Logger
    logger = Logger(True)
    logger.print("Initializing WDT")
    logger.set_wdt(WDT(timeout=config["SETTINGS"]["WDT_TIMEOUT"]))





def _read_crash_count():
    try:
        with open("crash_count.json", "r") as f:
            return json.load(f).get("count", 0)
    except (OSError, ValueError):
        return 0

def _write_crash_count(n):
    try:
        with open("crash_count.json", "w") as f:
            json.dump({"count": n}, f)
    except OSError:
        pass


CRASH_THRESHOLD = 3
MAX_TRACKED_CRASHES = 20
crash_count = min(_read_crash_count(), MAX_TRACKED_CRASHES)

if crash_count >= CRASH_THRESHOLD:
    print("Crash threshold reached (", crash_count, "), going to rescue")
    import rescue
    rescue.run(reason="crash_threshold")
else:
    try:
        import main
        _write_crash_count(crash_count + 1)
        print("main.py returned unexpectedly, treating as failure")
        import rescue
        rescue.run(reason="main_returned")
    except Exception as e:
        _write_crash_count(crash_count + 1)
        print("main.py crashed:", e)
        import rescue
        rescue.run(reason="exception", error=e)