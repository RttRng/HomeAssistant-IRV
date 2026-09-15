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