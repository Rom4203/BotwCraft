#!/usr/bin/env python3
"""Patch WiiXLaunch source to avoid nn::fs::OpenDirectory on unmounted sd:.

Confirmed crash (botwcraft(3).log, 2026-10-10):
MountSdCardForDebug("sd") => 0x320002; loader still probes
sd:/atmosphere/contents/... via DirectoryExists; Nintendo FS ABORTS
(ResultFsNotMounted 0x0035F202) instead of returning an error.

This must be applied to WiiXLaunch BEFORE building subsdk9. The fix
is in the common Candidates path resolver AND in the boot-time SD probe.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else "wiix")
fs = root / "include/wiixlaunch/fs.hpp"
entry = root / "src/switch_entry.cpp"

s = fs.read_text(encoding="utf-8")
needle = """    out[0] = path;
    out[1] = out[2] = out[3] = nullptr;
#if WIIXL_SWITCH
"""
replacement = """    out[0] = path;
    out[1] = out[2] = out[3] = nullptr;
#if WIIXL_SWITCH
    // BotwCraft / Ryujinx: MountSdCardForDebug may return 0x320002.
    // Even an EXPLICIT 'sd:/...' path is then fatal to nn::fs, because
    // Nintendo's FindFileSystem aborts with ResultFsNotMounted rather
    // than returning a normal failure from OpenDirectory.
    // Never expose this candidate while the SD mount is unavailable.
    if (IsSdPath(path) && !g_FSClientReady) {
        out[0] = nullptr;
        return;
    }
"""
assert s.count(needle) == 1, "FS::Candidates layout changed upstream"
fs.write_text(s.replace(needle, replacement), encoding="utf-8")

s = entry.read_text(encoding="utf-8")
needle = """    {
        char tidLower[sizeof(WiiXLaunch::Host::TitleId)];
"""
replacement = """    if (WiiXLaunch::FS::impl::g_FSClientReady) {
        // No SD mount -> no sd:/romfslite probes, even before the
        // Candidates guard above. This prevents the observed boot abort.
        char tidLower[sizeof(WiiXLaunch::Host::TitleId)];
"""
assert s.count(needle) == 1, "Switch loader ROMFSLITE layout changed upstream"
entry.write_text(s.replace(needle,replacement), encoding="utf-8")
print("Patched WiiXLaunch: sd:/ blocked when unmounted, ROMFSLITE boot probe guarded")
