from __future__ import annotations
import os
import time
import struct
import re
from pathlib import Path

# Read the combined BotwCraft launcher log FIRST. When launch.py starts
# Ryujinx, the emulator stdout (including WiiXLaunch OutputDebugString)
# is piped to BotwCraft/logs/botwcraft.log, NOT necessarily Ryujinx/Logs.
ROOT = Path(__file__).resolve().parent
GAME_ID = "01007ef00011e000"


def profiles():
    result = []
    for variable in ("APPDATA", "LOCALAPPDATA"):
        value = os.getenv(variable)
        if value:
            result.append(Path(value) / "Ryujinx")
    result += [Path("D:/Jeux/Emu/ryujinx/portable"),
               Path("D:/Jeux/Emu/ryujinx")]
    return result


def candidates():
    found = []
    seen = set()

    def add(p: Path):
        try:
            p = p.resolve()
            if p.is_file() and p not in seen:
                found.append(p)
                seen.add(p)
        except OSError:
            pass

    # Explicit input can be a log file or an extracted BotwCraft directory.
    given = os.environ.get("BOTWCRAFT_LOG", "").strip().strip('"')
    if given:
        p = Path(given)
        add(p if p.suffix.lower() == ".log" else p / "logs" / "botwcraft.log")

    # If the diagnostic sits next to an extracted BotwCraft installation.
    for root in (ROOT, ROOT.parent, ROOT.parent.parent):
        for rel in ("logs/botwcraft.log", "BotwCraft/logs/botwcraft.log",
                    "native/logs/botwcraft.log"):
            add(root / rel)

    # The user's known working BotwCraft location; bounded to nearby sessions.
    home = Path("D:/Jeux/Emu/botwcraft")
    if home.is_dir():
        add(home / "logs" / "botwcraft.log")
        for pattern in ("*/logs/botwcraft.log", "*/*/logs/botwcraft.log"):
            for p in home.glob(pattern):
                add(p)

    # Ryujinx stores its own logs separately if launched without the bridge.
    for p in profiles():
        for dirname in ("Logs", "logs"):
            d = p / dirname
            if d.is_dir():
                for log in d.glob("*.log"):
                    add(log)

    return found


def latest_log():
    all_logs = candidates()
    # Prefer a currently active BotwCraft session. The same diagnostic line
    # may otherwise exist in an older Ryujinx log and mislead the user.
    if not all_logs:
        return None
    return max(all_logs, key=lambda f: f.stat().st_mtime)


def read_latest_session(path: Path):
    # Show the diagnostic even if it started before the monitor window.
    data = path.read_bytes()[-2_000_000:]
    marker = data.rfind(b"Rust native BOTW session")
    if marker >= 0:
        data = data[marker:]
    return data.decode("utf-8", "replace")


def main():
    print("BOTWCRAFT : VERIFICATION PROFONDEUR NATiVE NVN", flush=True)
    print("Ce moniteur lit aussi le vrai logs/botwcraft.log de ton BotwCraft.", flush=True)
    current = None
    previous = ""
    start = time.monotonic()
    printed = set()
    first_wait = True
    count = 0
    while time.monotonic() - start < 180:
        log = latest_log()
        if log is None:
            if first_wait:
                print("Aucun journal trouvé automatiquement.", flush=True)
                print("Copie le chemin complet du fichier logs\\botwcraft.log :",
                      flush=True)
                path_text = input("> ").strip().strip('"')
                first_wait = False
                if path_text:
                    os.environ["BOTWCRAFT_LOG"] = path_text
            time.sleep(1)
            continue

        if current != log:
            current = log
            previous = ""
            printed.clear()
            print("\n[MONITEUR] Lecture du journal :", log, flush=True)

        try:
            content = read_latest_session(log)
        except (OSError, ValueError):
            time.sleep(.6)
            continue

        # Compare loader fingerprint with the actual module in this ZIP.
        # A loaded old probe is easy to mistake for a broken callback.
        local_probe=ROOT/"bwc_depth_probe.wxlm"
        if local_probe.exists():
            try:
                expected=struct.unpack_from("<I",local_probe.read_bytes(),40)[0]
                matches=re.findall(r"\[loader:bwc_depth_probe\] integrity OK \(crc32 0x([0-9A-Fa-f]+)", content)
                if matches:
                    actual=int(matches[-1],16)
                    marker=("module-collision",expected,actual)
                    if marker not in printed:
                        printed.add(marker)
                        if actual!=expected:
                            print("[DIAGNOSTIC] ANCIEN MODULE DETECTE : Ryujinx 0x%08X ; ZIP 0x%08X" %
                                  (actual,expected),flush=True)
                            print("Ferme Ryujinx et relance INSTALLER_COMPLET.bat : I, puis redemarre le jeu.",
                                  flush=True)
                        else:
                            print("[DIAGNOSTIC] BON MODULE : CRC 0x%08X confirme dans Ryujinx" % expected,
                                  flush=True)
            except (OSError,ValueError,struct.error):
                pass
        # This log is appended to by the standard BotwCraft Python launcher.
        # Keep track of printed rows, including across the first read.
        for line in content.splitlines():
            if "[DEPTH_PROBE]" in line or (
                "[loader:bwc_depth_probe] LOADED" in line
            ):
                if line not in printed:
                    print(line[-550:], flush=True)
                    printed.add(line)
                    count += 1

        if content != previous:
            previous = content
        elif count == 0 and time.monotonic() - start > 12 and first_wait:
            first_wait = False
            print("[MONITEUR] Aucun message DEPTH_PROBE pour cette session.",
                  flush=True)
            print("Le module peut être absent, ou son hook n'est pas exécuté.",
                  flush=True)
            print("Tu peux déjà m'envoyer ce logs\\botwcraft.log.", flush=True)
        time.sleep(.7)

    print("Surveillance terminée. Envoie-moi les lignes [DEPTH_PROBE],")
    print("ou le fichier logs\\botwcraft.log si aucune n'apparaît.")


if __name__ == "__main__":
    main()
