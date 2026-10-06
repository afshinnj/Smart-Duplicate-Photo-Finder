"""Self-extracting installer generator for DupliPix (تشخیص عکس‌های تکراری).

Emits ``dist/DupliPix-Setup.exe``: a single file that, when
run on a clean Windows machine, extracts the PyInstaller ``onedir`` tree into
``%LOCALAPPDATA%\Programs\DupliPix`` and creates Start Menu +
Desktop shortcuts pointing at the bundled ``DupliPix.exe``.

The payload is a plain zip archive appended after a small launcher stub, so the
distribution stays a single file with no external tooling required.
"""

from __future__ import annotations

import io
import os
import shutil
import struct
import sys
import zipfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_APP_NAME = "DupliPix"
_EXE_NAME = f"{_APP_NAME}.exe"


def _build_launcher(out_path: Path) -> None:
    """Write the C# installer launcher that the .NET compiler builds in place."""
    body = r"""
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;

class Installer
{
    static string EnvOrFolder(string name, Environment.SpecialFolder folder)
    {
        // ``GetFolderPath`` ignores overridden profile env vars, so read the
        // variable first and fall back to the shell folder on a real desktop.
        string value = Environment.GetEnvironmentVariable(name);
        if (!string.IsNullOrEmpty(value) && Directory.Exists(value))
        {
            return value;
        }
        return Environment.GetFolderPath(folder);
    }

    static string StartMenuDir()
    {
        // Per-user Start Menu: the common (all-users) folder needs elevation,
        // and this installer deliberately installs without admin rights.
        string programs = Environment.GetFolderPath(Environment.SpecialFolder.Programs);
        if (string.IsNullOrEmpty(programs))
        {
            string userProfile = EnvOrFolder("USERPROFILE", Environment.SpecialFolder.UserProfile);
            if (!string.IsNullOrEmpty(userProfile))
            {
                programs = Path.Combine(userProfile,
                    "AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs");
            }
        }
        return string.IsNullOrEmpty(programs) ? null : Path.Combine(programs, "@APP_NAME@");
    }

    static string DesktopDir()
    {
        string desktop = EnvOrFolder("USERPROFILE", Environment.SpecialFolder.DesktopDirectory);
        if (string.IsNullOrEmpty(desktop) || !Directory.Exists(desktop))
        {
            string userProfile = EnvOrFolder("USERPROFILE", Environment.SpecialFolder.UserProfile);
            if (!string.IsNullOrEmpty(userProfile))
            {
                desktop = Path.Combine(userProfile, "Desktop");
            }
        }
        return desktop;
    }

    static string ResolveInstallDir()
    {
        string localAppData = EnvOrFolder("LOCALAPPDATA", Environment.SpecialFolder.LocalApplicationData);
        if (string.IsNullOrEmpty(localAppData))
        {
            localAppData = Path.Combine(
                EnvOrFolder("USERPROFILE", Environment.SpecialFolder.UserProfile),
                "AppData", "Local");
        }
        return Path.Combine(localAppData, "Programs", "@APP_NAME@");
    }

    static int Main(string[] args)
    {
        string installDir = ResolveInstallDir();

        bool quiet = Array.IndexOf(args, "/S") >= 0;
        bool uninstall = Array.IndexOf(args, "/U") >= 0;

        if (uninstall)
        {
            return Uninstall(installDir, quiet);
        }

        // A redirected or absent console makes even the title setter throw.
        try { Console.Title = "@APP_NAME@ Setup"; }
        catch { }
        if (!quiet)
        {
            try { Console.WriteLine("=== @APP_NAME@ Setup ==="); }
            catch { }
        }
        try
        {
            Directory.CreateDirectory(installDir);

            string self = Assembly.GetExecutingAssembly().Location;
            using (var stream = new FileStream(self, FileMode.Open, FileAccess.Read))
            {
                var reader = new BinaryReader(stream);
                stream.Seek(-8, SeekOrigin.End);
                long zipLength = reader.ReadInt64();
                stream.Seek(-(8 + zipLength), SeekOrigin.End);

                var buffer = new byte[zipLength];
                int read = 0;
                while (read < zipLength)
                {
                    read += reader.Read(buffer, read, (int)zipLength - read);
                }

                var zip = new System.IO.Compression.ZipArchive(
                    new MemoryStream(buffer), System.IO.Compression.ZipArchiveMode.Read);
                foreach (var entry in zip.Entries)
                {
                    string dest = Path.Combine(installDir, entry.FullName);
                    string dir = Path.GetDirectoryName(dest);
                    if (!string.IsNullOrEmpty(dir))
                    {
                        Directory.CreateDirectory(dir);
                    }
                    if (entry.FullName.EndsWith("/") || entry.FullName.EndsWith("\\"))
                    {
                        continue;
                    }
                    using (var entryStream = entry.Open())
                    using (var outStream = new FileStream(dest, FileMode.Create, FileAccess.Write))
                    {
                        entryStream.CopyTo(outStream);
                    }
                }
            }

            CreateShortcuts(installDir);

            if (!quiet)
            {
                try
                {
                    Console.WriteLine("Installed to: " + installDir);
                    Console.WriteLine("Launch with the Start Menu or Desktop shortcut.");

                    bool launch = args.Length == 0 || Array.IndexOf(args, "/NOLAUNCH") < 0;
                    if (launch)
                    {
                        Process.Start(Path.Combine(installDir, "@EXE_NAME@"));
                    }
                    else
                    {
                        Console.WriteLine("Press any key to exit.");
                        Console.ReadKey();
                    }
                }
                catch { }
            }
            return 0;
        }
        catch (Exception ex)
        {
            try
            {
                Console.Error.WriteLine("Installation failed: " + ex.Message);
                if (!quiet)
                {
                    Console.WriteLine("Press any key to exit.");
                    Console.ReadKey();
                }
            }
            catch { }
            return 1;
        }
    }

    static void CreateShortcuts(string installDir)
    {
        string exe = Path.Combine(installDir, "@EXE_NAME@");

        string startMenu = StartMenuDir();
        if (string.IsNullOrEmpty(startMenu))
        {
            return;
        }
        Directory.CreateDirectory(startMenu);

        string desktop = DesktopDir();

        // WScript.Shell is invoked through plain reflection: the late-bound
        // ``dynamic`` keyword pulls in Microsoft.CSharp.dll, which is not
        // guaranteed to be present on a bare .NET Framework install.
        Type shellType = Type.GetTypeFromProgID("WScript.Shell");
        if (shellType == null)
        {
            return;
        }
        object shell = Activator.CreateInstance(shellType);

        var targets = new System.Collections.Generic.List<string> { startMenu };
        if (!string.IsNullOrEmpty(desktop))
        {
            targets.Add(desktop);
        }

        foreach (string dir in targets)
        {
            string link = Path.Combine(dir, "@APP_NAME@.lnk");
            try
            {
                object shortcut = shellType.InvokeMember(
                    "CreateShortcut",
                    System.Reflection.BindingFlags.InvokeMethod, null, shell, new object[] { link });
                Type shortcutType = shortcut.GetType();
                shortcutType.InvokeMember("TargetPath",
                    System.Reflection.BindingFlags.SetProperty, null, shortcut, new object[] { exe });
                shortcutType.InvokeMember("WorkingDirectory",
                    System.Reflection.BindingFlags.SetProperty, null, shortcut, new object[] { installDir });
                shortcutType.InvokeMember("Description",
                    System.Reflection.BindingFlags.SetProperty, null, shortcut, new object[] { "@APP_NAME@" });
                shortcutType.InvokeMember("IconLocation",
                    System.Reflection.BindingFlags.SetProperty, null, shortcut,
                    new object[] { Path.Combine(installDir, "app_icon.ico") });
                shortcutType.InvokeMember("Save",
                    System.Reflection.BindingFlags.InvokeMethod, null, shortcut, null);
            }
            catch
            {
                /* a shortcut must never abort the install */
            }
        }
    }

    static int Uninstall(string installDir, bool quiet)
    {
        try
        {
            foreach (var proc in Process.GetProcessesByName("@APP_NAME@"))
            {
                proc.Kill();
                proc.WaitForExit(3000);
            }
        }
        catch { }

        if (Directory.Exists(installDir))
        {
            for (int attempt = 0; attempt < 10; attempt++)
            {
                try { Directory.Delete(installDir, true); break; }
                catch { System.Threading.Thread.Sleep(500); }
            }
        }

        string startMenu = StartMenuDir();
        if (!string.IsNullOrEmpty(startMenu) && Directory.Exists(startMenu))
        {
            Directory.Delete(startMenu, true);
        }

        string desktopLink = null;
        string desktop = DesktopDir();
        if (!string.IsNullOrEmpty(desktop))
        {
            desktopLink = Path.Combine(desktop, "@APP_NAME@.lnk");
        }
        if (!string.IsNullOrEmpty(desktopLink) && File.Exists(desktopLink))
        {
            File.Delete(desktopLink);
        }

        if (!quiet)
        {
            Console.WriteLine("Removed " + installDir);
        }
        return 0;
    }
}
""".lstrip()
    body = body.replace("@APP_NAME@", _APP_NAME).replace("@EXE_NAME@", _EXE_NAME)
    out_path.write_text(body, encoding="utf-8")


def _zip_payload(dist_dir: Path) -> bytes:
    """Zip the package with the exe at the archive root (no parent folder)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(dist_dir.rglob("*")):
            if path.is_dir():
                continue
            relative = path.relative_to(dist_dir)
            archive.write(path, relative.as_posix())
        # Root-level copy so the shortcut icon resolves next to the exe.
        icon_path = _HERE / "assets" / "icons" / "app_icon.ico"
        if icon_path.is_file():
            archive.write(icon_path, "app_icon.ico")
    return buffer.getvalue()


def build() -> Path:
    dist_dir = _HERE / "dist" / _APP_NAME
    if not dist_dir.is_dir():
        raise SystemExit(f"Packaged app not found: {dist_dir}")

    payload = _zip_payload(dist_dir)
    stage = _HERE / "dist" / "installer_stage"
    if stage.is_dir():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    launcher_cs = stage / "Installer.cs"
    _build_launcher(launcher_cs)

    icon = _HERE / "assets" / "icons" / "app_icon.ico"
    exe_out = stage / _EXE_NAME

    # Compile the launcher with the .NET C# compiler, embedding the icon.
    csc_candidates = [
        r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
        r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe",
    ]
    csc = next((p for p in csc_candidates if os.path.isfile(p)), None)
    if csc is None:
        raise SystemExit("No .NET C# compiler (csc.exe) found on this machine.")

    import subprocess

    args = [
        csc,
        "/nologo",
        "/target:winexe",
        f"/out:{exe_out}",
        f"/win32icon:{icon}",
        "/reference:System.IO.Compression.dll",
        "/reference:System.IO.Compression.FileSystem.dll",
    ]
    result = subprocess.run(args + [str(launcher_cs)], capture_output=True, text=True)
    if result.returncode != 0 or not exe_out.is_file():
        raise SystemExit(f"C# compilation failed:\n{result.stdout}\n{result.stderr}")

    setup = _HERE / "dist" / f"{_APP_NAME}-Setup.exe"
    with open(exe_out, "rb") as handle:
        launcher_bytes = handle.read()

    with open(setup, "wb") as handle:
        handle.write(launcher_bytes)
        handle.write(payload)
        handle.write(struct.pack("<Q", len(payload)))

    print(f"Installer written: {setup} ({setup.stat().st_size / 1024 / 1024:.1f} MB)")
    return setup


if __name__ == "__main__":
    build()
