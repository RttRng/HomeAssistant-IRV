def _channel(config):
    settings = config["SETTINGS"]
    if settings["CHANNEL"] == "unstable":
        return "unstable"
    if settings["CHANNEL"] == "stable":
        return "stable"
    return "tested"
    
def _sha256_hex(data):
    import uhashlib
    h = uhashlib.sha256()
    h.update(data)
    import ubinascii
    return ubinascii.hexlify(h.digest()).decode()


def update(version, config, logger):
    try:
        logger.wdt.feed()
        import urequests
        import uhashlib
        import os

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

        logger.wdt.feed()
        response = urequests.get(channel_url + "checksums.json", headers=headers)
        if response.status_code != 200:
            response.close()
            return "Failed to fetch checksums: " + str(response.status_code)
        checksums = response.json()
        response.close()

        # Stage every file under /_ota_stage/, verify each against its
        # checksum, and only rename into the real destination once ALL
        # files have downloaded and verified cleanly. This means a failure
        # partway through leaves the live filesystem completely untouched -
        # no more half-updated boards.
        stage_dir = "/_ota_stage"
        try:
            os.mkdir(stage_dir)
        except OSError as e:
            if e.args[0] != 17:  # not EEXIST
                return "Failed to create staging directory"

        for d in manifest["dirs"]:
            logger.wdt.feed()
            try:
                os.mkdir(dest_dir := "/" + d)
            except OSError as e:
                if e.args[0] != 17:
                    return "Failed to create directory: " + d

        staged = []  # list of (stage_path, dest_path)
        version_file_info = None

        try:
            for file_info in manifest["files"]:
                name = file_info["name"]
                path = file_info["path"]
                key = path + name

                if path == "" and name == "version.json":
                    version_file_info = file_info
                    continue

                dest = "/" + path + name
                stage_path = stage_dir + "/" + key.replace("/", "_")

                expected = checksums.get(key)
                if expected is None:
                    return "Missing checksum for " + key + ", aborting"

                logger.print("Downloading", name, "to", dest)
                logger.wdt.feed()
                resp = urequests.get(channel_url + path + name, headers=headers)
                if resp.status_code != 200:
                    resp.close()
                    return "Failed to download file: " + name + " " + str(resp.status_code)
                data = resp.content
                resp.close()

                actual = _sha256_hex(data)
                if actual != expected:
                    return ("Checksum mismatch for " + key +
                            " (expected " + expected + ", got " + actual + "), aborting")

                with open(stage_path, "wb") as f:
                    f.write(data)

                staged.append((stage_path, dest))

            if version_file_info is None:
                return "Manifest missing version.json entry"

            # All files downloaded and verified. Now install: rename each
            # staged file into place. This is now just a filesystem
            # rename per file, no network involved, so failures here are
            # extremely unlikely and not worth staging further.
            logger.wdt.feed()
            for stage_path, dest in staged:
                os.rename(stage_path, dest)

        finally:
            # Clean up any leftover staged files (successful ones were
            # already moved out; this mops up after an aborted update).
            for f in os.listdir(stage_dir):
                try:
                    os.remove(stage_dir + "/" + f)
                except OSError:
                    pass

        # Fetch + verify version.json last, same as before - only once this
        # is written does the board consider itself on the new version.
        logger.wdt.feed()
        resp = urequests.get(channel_url + "version.json", headers=headers)
        if resp.status_code != 200:
            resp.close()
            return "Failed to re-fetch version.json: " + str(resp.status_code)
        raw = resp.content
        resp.close()

        expected = checksums.get("version.json")
        if expected and _sha256_hex(raw) != expected:
            return "version.json checksum mismatch on final fetch, aborting"

        try:
            confirmed = json.loads(raw)
        except Exception as e:
            return "version.json fetched but invalid JSON: " + str(e)

        if confirmed["version"] != new_version["version"]:
            return "version.json changed mid-update, aborting (server moved on?)"

        with open("/version.json.part", "wb") as f:
            f.write(raw)
        os.rename("/version.json.part", "/version.json")

        logger.print("Update completed successfully!")
        from crash_lib import *
        _write_crash_count(0)

        import machine
        machine.reset()
    except Exception as e:
        return "Update failed: " + str(e)