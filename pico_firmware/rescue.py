"""Rescue kernel. Deliberately standalone - must not import anything from
main.py/irv_lib.py. Does exactly one bounded pass (connect, distress ping,
one update check) then always reboots. boot.py decides on the next boot
whether to try main.py again or come straight back here.
"""
import network
import time
import machine
import json

REBOOT_DELAY_S = 90

def _connect_wifi(logger, credentials, max_attempts=10):
    wlan = network.WLAN(network.STA_IF)
    try:
        wlan.deinit()
    except Exception:
        pass
    wlan.active(True)
    for attempt in range(max_attempts):
        logger.wdt.feed()
        nets = wlan.scan()
        best_net, best_rssi = None, -999
        for ssid_bytes, *_rest, rssi, _authmode, _hidden in nets:
            ssid = ssid_bytes.decode()
            if ssid in credentials and rssi > best_rssi:
                best_net, best_rssi = ssid, rssi
        if best_net:
            wlan.connect(best_net, credentials[best_net])
            timeout = 15
            while not wlan.isconnected() and timeout > 0:
                time.sleep(1)
                logger.wdt.feed()
                timeout -= 1
            if wlan.isconnected():
                return True
        time.sleep(2)
    return False

def _read_json(path):
    with open(path, "r") as f:
        return json.load(f)


def _safe(fn, default="unknown"):
    """Run fn() and swallow any exception, returning default instead.

    Used so that one missing/failing diagnostic (e.g. no WLAN handle yet,
    or a platform without a given machine call) never prevents the rest
    of the distress payload from being sent.
    """
    try:
        return fn()
    except Exception:
        return default


def _collect_diagnostics(reason, error, version):
    """Gather everything useful for triaging a rescue-mode boot.

    Kept as a flat dict of str -> str so it can be turned straight into a
    query string; every value is computed defensively via _safe() since
    this runs in an already-degraded state and must never itself raise.
    """
    import gc
    from crash_lib import read_crash_count

    diag = {}
    diag["reason"] = reason
    diag["error"] = str(error)[:120]
    diag["version"] = str(version.get("version", "unknown"))
    diag["crash_count"] = str(_safe(read_crash_count, 0))

    diag["reset_cause"] = _safe(lambda: str(machine.reset_cause()))

    diag["mem_free"] = _safe(lambda: str(gc.mem_free()))
    diag["mem_alloc"] = _safe(lambda: str(gc.mem_alloc()))

    def _rssi():
        wlan = network.WLAN(network.STA_IF)
        return str(wlan.status("rssi")) if wlan.isconnected() else "not_connected"
    diag["wifi_rssi"] = _safe(_rssi)

    diag["ip"] = _safe(lambda: network.WLAN(network.STA_IF).ifconfig()[0])

    diag["uptime_ms"] = _safe(lambda: str(time.ticks_ms()))

    return diag


def _urlencode(value):
    """Minimal percent-encoding, since MicroPython has no urllib.parse.

    Only needs to be safe enough for our own diagnostic values (error
    strings, reset-cause names, etc.) which may contain spaces, colons,
    or other characters that would otherwise break the query string.
    """
    out = []
    safe = "-_.~"
    for ch in value:
        if ch.isalpha() or ch.isdigit() or ch in safe:
            out.append(ch)
        else:
            out.append("%{:02X}".format(ord(ch)))
    return "".join(out)


def _ping_distress(reason, error, version):
    try:
        import urequests
        with open("api.key", "r") as f:
            key = f.read().strip()
        with open("base_url.txt", "r") as f:
            base_url = f.read().strip()
        with open("identity.txt", "r") as f:
            board = f.read().strip()

        diag = _collect_diagnostics(reason, error, version)
        diag["board"] = board

        query = "&".join(k + "=" + _urlencode(v) for k, v in diag.items())
        url = base_url + "rescue_ping?" + query

        resp = urequests.get(url, headers={"X-API-KEY": key})
        resp.close()
    except Exception as e:
        print("distress ping failed (non-fatal):", e)


def reboot_with_delay(logger, delay):
    waiting = 0
    while waiting < delay:
        logger.wdt.feed()
        time.sleep(5)
        waiting += 5
    machine.reset()


def run(logger,reason="unknown", error=""):
    print("=== RESCUE MODE ===", reason, error)
    logger.wdt.feed()
    try:
        identity = open("identity.txt").read().strip()
        wifi_config = _read_json("wifi.json")
        version = _read_json("version.json")
        config = _read_json(f"/branches/{identity}/config.json")
    except Exception as e:
        print("rescue: couldn't read local config:", e)
        reboot_with_delay(logger,REBOOT_DELAY_S)
    logger.wdt.feed()
    if _connect_wifi(logger,wifi_config):
        logger.wdt.feed()
        _ping_distress(reason, error, version)
        logger.wdt.feed()
        try:
            logger.wdt.feed()
            import pull
            result = pull.update(version,config,logger)
            print("rescue: pull result:", result)
        except Exception as e:
            print("rescue: pull.update() itself raised:", e)
    else:
        print("rescue: WiFi failed this pass")

    print("rescue: pass complete, rebooting in", REBOOT_DELAY_S, "s")
    reboot_with_delay(logger,REBOOT_DELAY_S)