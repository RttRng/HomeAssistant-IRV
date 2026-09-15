def _channel(config):
    settings = config["SETTINGS"]
    if settings["CHANNEL"] == "unstable":
        return "unstable"
    if settings["CHANNEL"] == "stable":
        return "stable"
    return "tested"


def update(version, config, logger):
    try:
        logger.wdt.feed()
        import urequests
        with open("api.key", "r") as f:
            key = f.read().strip()
        with open("base_url.txt", "r") as f:
            base_url = f.read().strip()

        channel = _channel(config)
        channel_url = base_url + channel + "/"
        headers = {"X-API-KEY": key}

        logger.wdt.feed()
        response = urequests.get(channel_url + "version.json", headers=headers)
        if response.status_code == 503:
            response.close()
            return "Release not ready, skipping"
        if response.status_code != 200:
            response.close()
            return "Failed to fetch version: " + str(response.status_code)
        new_version = response.json()
        response.close()
        logger.print("Version:", new_version)

        if new_version["version"] == version["version"]:
            return "Already at this version, skipping"

        logger.wdt.feed()
        response = urequests.get(channel_url + "manifest.json", headers=headers)
        if response.status_code == 503:
            response.close()
            return "Release not ready, skipping"
        if response.status_code != 200:
            response.close()
            return "Failed to fetch manifest: " + str(response.status_code)
        manifest = response.json()
        response.close()
        logger.print("Manifest fetched!")

        import os
        for dir in manifest["dirs"]:
            logger.wdt.feed()
            try:
                os.mkdir(dir)
            except OSError as e:
                if e.args[0] != 17:  # not EEXIST
                    return "Failed to create directory: " + dir

        version_file_info = None
        for file_info in manifest["files"]:
            name = file_info["name"]
            path = file_info["path"]

            # version.json is committed last, only once everything else
            # has succeeded - see below.
            if path == "" and name == "version.json":
                version_file_info = file_info
                continue

            dest = "/" + path + name
            tmp = dest + ".part"

            logger.print("Downloading", name, "to", dest)
            logger.wdt.feed()
            resp = urequests.get(channel_url + path + name, headers=headers)
            if resp.status_code != 200:
                resp.close()
                return "Failed to download file: " + name + " " + str(resp.status_code)

            with open(tmp, "wb") as f:
                f.write(resp.content)
            resp.close()
            os.rename(tmp, dest)

        if version_file_info is None:
            return "Manifest missing version.json entry"

        # Fetch + verify version.json last. Only once this is written does
        # the board consider itself "on" the new version - so a failure
        # anywhere above leaves the board's local version.json untouched,
        # and the next boot will retry the same update instead of thinking
        # it's already done.
        logger.wdt.feed()
        resp = urequests.get(channel_url + "version.json", headers=headers)
        if resp.status_code != 200:
            resp.close()
            return "Failed to re-fetch version.json: " + str(resp.status_code)
        raw = resp.content
        resp.close()

        try:
            import json
            confirmed = json.loads(raw)
        except Exception as e:
            return "version.json fetched but invalid JSON: " + str(e)

        if confirmed["version"] != new_version["version"]:
            return "version.json changed mid-update, aborting (server moved on?)"

        with open("/version.json.part", "wb") as f:
            f.write(raw)
        import os
        os.rename("/version.json.part", "/version.json")

        logger.print("Update completed successfully!")
        from crash_lib import *

        _write_crash_count(0)

        import machine
        machine.reset()
    except Exception as e:
        return "Update failed: " + str(e)