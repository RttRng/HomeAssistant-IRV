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

def _ping_distress(reason, error, version):
    try:
        import urequests
        with open("api.key", "r") as f:
            key = f.read().strip()
        with open("base_url.txt", "r") as f:
            base_url = f.read().strip()
        with open("identity.txt", "r") as f:
            board = f.read().strip()
        url = (base_url + "rescue_ping"
               + "?board=" + board
               + "&version=" + str(version.get("version", "unknown"))
               + "&reason=" + reason
               + "&error=" + str(error)[:120])
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
        return
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