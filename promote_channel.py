#!/usr/bin/env python3
"""promote_channel.py

Points a channel (stable / tested / unstable) at a specific, already-
published release. Only touches the small latest_<channel>.txt pointer
files - never touches release folders themselves.

Hierarchy: tested <= stable <= unstable (unstable gets things first/most
often, tested is the most conservative/slowest-moving). Promoting a more
conservative channel forward automatically bumps any less-conservative
channel that's currently behind it - e.g. promoting 'stable' to 3.9.3 will
also bump 'unstable' to 3.9.3 if unstable was still behind.

Examples:
    promote_channel.py --releases-root ./releases unstable 3.9.3
    promote_channel.py --releases-root ./releases stable --latest
    promote_channel.py --releases-root ./releases --show
    promote_channel.py --releases-root ./releases tested 3.9.2 --force
"""
import argparse
import os
import re
import sys
import tempfile

# Ordered from most conservative to least conservative. Index = rank.
CHANNELS = ("tested", "stable", "unstable")


def parse_version(v):
    """Parse a dotted version string into a tuple of ints for comparison.
    Falls back to comparing raw strings (with a warning) if it doesn't
    look numeric, so weird version strings don't crash the script."""
    parts = v.strip().split(".")
    if all(re.fullmatch(r"\d+", p) for p in parts):
        return tuple(int(p) for p in parts)
    return None  # signals "not comparable numerically"


def version_less_than(a, b):
    """True if version a < version b. Falls back to string comparison
    with a warning if either doesn't parse as dotted integers."""
    pa, pb = parse_version(a), parse_version(b)
    if pa is None or pb is None:
        print(f"WARNING: comparing non-numeric versions ({a!r}, {b!r}) "
              f"as plain strings, ordering may be wrong.")
        return a < b
    return pa < pb


def pointer_path(releases_root, channel):
    return os.path.join(releases_root, f"latest_{channel}.txt")


def read_pointer(releases_root, channel):
    path = pointer_path(releases_root, channel)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return f.read().strip() or None


def write_pointer_atomic(releases_root, channel, version):
    path = pointer_path(releases_root, channel)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{channel}-", dir=releases_root)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(version)
        os.rename(tmp_path, path)  # atomic, same filesystem
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def release_is_ready(releases_root, version):
    release_dir = os.path.join(releases_root, version)
    return os.path.isdir(release_dir) and os.path.exists(os.path.join(release_dir, ".ready"))


def list_ready_releases(releases_root):
    out = []
    for entry in os.scandir(releases_root):
        if not entry.is_dir():
            continue
        ready_file = os.path.join(entry.path, ".ready")
        if os.path.exists(ready_file):
            out.append((entry.name, os.path.getmtime(ready_file)))
    return out


def most_recent_release(releases_root):
    releases = list_ready_releases(releases_root)
    if not releases:
        return None
    releases.sort(key=lambda pair: pair[1])
    return releases[-1][0]


def show_pointers(releases_root):
    print(f"{'channel':<10} version")
    print("-" * 24)
    for channel in CHANNELS:
        current = read_pointer(releases_root, channel)
        print(f"{channel:<10} {current or '(unset)'}")
    latest = most_recent_release(releases_root)
    print()
    print(f"most recently published release: {latest or '(none)'}")


def apply_hierarchy(releases_root, from_channel, version, force):
    """After promoting from_channel to version, cascade forward through
    any less-conservative channel (higher CHANNELS index) that's
    currently behind. Returns list of (channel, old, new) actually
    changed, for logging."""
    changes = []
    start = CHANNELS.index(from_channel)
    for channel in CHANNELS[start:]:
        current = read_pointer(releases_root, channel)
        if current == version:
            continue
        if current is not None and not force and version_less_than(version, current):
            # cascading channel is already further ahead than us - leave
            # it alone, this isn't a downgrade situation for it.
            continue
        write_pointer_atomic(releases_root, channel, version)
        changes.append((channel, current, version))
    return changes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--releases-root", default=os.path.dirname(__file__)+"/releases",
                         help="path to OTA server's releases/ dir")
    parser.add_argument("channel", nargs="?", choices=CHANNELS,
                         help="most conservative channel to update; less "
                              "conservative channels behind it cascade forward")
    parser.add_argument("version", nargs="?",
                         help="version to point the channel at")
    parser.add_argument("--latest", action="store_true",
                         help="use the most recently published release "
                              "instead of an explicit version")
    parser.add_argument("--show", action="store_true",
                         help="print current pointer for every channel and exit")
    parser.add_argument("--no-cascade", action="store_true",
                         help="only update the given channel, skip the "
                              "automatic tested<=stable<=unstable cascade")
    parser.add_argument("--force", action="store_true",
                         help="allow moving a channel backwards, and skip "
                              "the forward-cascade ordering check")
    args = parser.parse_args()

    if not os.path.isdir(args.releases_root):
        parser.error(f"releases_root does not exist: {args.releases_root}")

    if args.show:
        show_pointers(args.releases_root)
        return

    if not args.channel:
        parser.error("channel is required unless --show is given")

    if args.version and args.latest:
        parser.error("pass either a version or --latest, not both")

    if args.latest:
        version = most_recent_release(args.releases_root)
        if version is None:
            print(f"No published releases found under {args.releases_root}")
            sys.exit(1)
        print(f"--latest resolved to {version}")
    elif args.version:
        version = args.version
    else:
        parser.error("version or --latest is required unless --show is given")

    if not release_is_ready(args.releases_root, version):
        print(f"ERROR: release {version} is not published/ready under "
              f"{args.releases_root}. Run publish_release.py first.")
        sys.exit(1)

    current = read_pointer(args.releases_root, args.channel)
    if current == version:
        print(f"{args.channel} is already at {version}, nothing to do.")
        return

    if current is not None and not args.force and version_less_than(version, current):
        print(f"WARNING: {version} looks older than current "
              f"{args.channel} ({current}). Use --force to proceed anyway.")
        sys.exit(1)

    write_pointer_atomic(args.releases_root, args.channel, version)
    print(f"{args.channel} -> {version} (was {current or 'unset'})")

    if not args.no_cascade:
        changes = apply_hierarchy(args.releases_root, args.channel, version, args.force)
        for channel, old, new in changes:
            if channel == args.channel:
                continue  # already printed above
            print(f"  cascaded: {channel} -> {new} (was {old or 'unset'})")


if __name__ == "__main__":
    main()