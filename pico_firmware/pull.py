def update(version,config,logger):
    try:
        logger.wdt.feed()
        import urequests
        with open("api.key", "r") as f:
            key = f.read().strip()
        with open("base_url.txt", "r") as f:
            base_url = f.read().strip()
        url = base_url+"version.json"
        headers = {"X-API-KEY": key}
        logger.wdt.feed()
        response = urequests.get(url, headers=headers)
        new_version = {}
        if response.status_code == 200:
            new_version = response.json()
            logger.print("Version fetched!")
        else:
            response.close()
            return "Failed to fetch version: " + str(response.status_code)
        response.close()
        logger.print("Version:", new_version)
        use_untested = config["SETTINGS"]["USE_UNTESTED"]
        use_unstable = config["SETTINGS"]["USE_UNSTABLE"]
        if not use_untested and not new_version["tested"]:
            return "Untested version"
        if not use_unstable and not new_version["stable"]:
            return "Unstable version"
        if new_version["version"] == version["version"]:
            return "Already at this version, skipping"
        
        url = base_url+"manifest.json"
        headers = {"X-API-KEY": key}
        logger.wdt.feed()
        response = urequests.get(url, headers=headers)
        manifest = {}
        if response.status_code == 200:
            manifest = response.json()
            logger.print("Manifest fetched!")
        else:
            response.close()
            return "Failed to fetch manifest: " + str(response.status_code)
        response.close()
        print("Manifest:", manifest)
        import os
        dirs = manifest["dirs"]
        logger.wdt.feed()
        for dir in dirs:
            try:
                os.mkdir(dir)
            except OSError as e:
                if e.args[0] == 17:  # EEXIST
                    pass
                else:
                    return "Failed to create directory: " + dir
        logger.wdt.feed()
        for file_info in manifest["files"]:
            name = file_info["name"]
            path = file_info["path"]
            logger.print("Downloading", name, "to", "/"+path) 
            logger.wdt.feed()
            resp = urequests.get(base_url+path+name, headers=headers)
            if resp.status_code != 200:
                resp.close()
                return "Failed to download file: " + name + " " + str(resp.status_code)
            with open("/"+path+name, "w") as f:
                f.write(resp.content)
            resp.close()
        logger.print("Update completed successfully!")
        import machine
        machine.reset()
    except Exception as e:
        return "Update failed: " + str(e)