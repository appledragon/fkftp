# FKFTP

A minimal FTP server with a web-based management UI.

## Why?

Copying files across a LAN should be simple. But Windows 11 tightened its SMB sharing security policies, and logging in with a Microsoft account makes network share authentication and permissions incredibly painful to configure. After hours of frustration, I decided to just write a dead-simple FTP server — **no Windows sharing policies to wrestle with, launch it and it works, configure everything from a browser.**

## Features

- **Web Management UI** — configure everything in the browser, no config files to edit
- **Multi-directory Mounting** — each user can map multiple directories across different drives into a unified virtual directory tree
- **SHA-256 Password Hashing** — passwords are never stored in plain text
- **Fine-grained Permissions** — 8 permission flags per user (list, download, upload, delete, rename, etc.)
- **One-click Firewall Setup** — add/remove Windows Firewall rules directly from the Web UI
- **Windows Service** — register as a system service for auto-start on boot
- **Single-file Deployment** — PyInstaller packages everything into one executable, copy it anywhere and run
- **Cross-platform** — runs on Windows, macOS, and Linux
- **Multi-language UI** — Web interface supports Chinese and English

## Quick Start

### Run Directly

```
fkftp.exe
```

A browser will automatically open `http://127.0.0.1:8080` with the management UI.

### Run from Source

```bash
pip install -r requirements.txt
python app.py
```

### Build

Windows:
```bash
build.bat
```

macOS / Linux:
```bash
chmod +x build.sh
./build.sh
```

The resulting executable will be in the `dist/` directory.

> **Note:** Firewall management and Windows Service features are only available on Windows. On macOS/Linux these panels are automatically hidden. The core FTP server works identically on all platforms.

## Usage

1. Run `fkftp.exe` (or `python app.py`)
2. Add a user in the Web UI, set a password and permissions
3. Configure directory mappings for the user (can map folders from different drives)
4. Save the configuration and start the FTP server
5. Connect with any FTP client (Windows Explorer, FileZilla, etc.)

## Connecting via FTP

In the Windows Explorer address bar, type:

```
ftp://your-ip:2121
```

Or use any FTP client such as FileZilla.

## Windows Service

> This feature is only available on Windows.

Click "Install Service" in the Web UI, or use the command line:

```bash
fkftp.exe --service install   # Install (requires admin)
fkftp.exe --service start     # Start
fkftp.exe --service stop      # Stop
fkftp.exe --service uninstall # Uninstall
```

## Project Structure

```
app.py           # Flask web management backend
server.py        # FTP server core (pyftpdlib)
filesystem.py    # Multi-directory virtual filesystem
service.py       # Windows service registration (Windows only)
hash_password.py # Password hashing utility
config.json      # Runtime config (auto-generated)
build.bat        # Windows build script
build.sh         # macOS/Linux build script
templates/
  index.html     # Web management UI (single-page app)
tests/           # Unit tests
```

## Dependencies

- [pyftpdlib](https://github.com/giampaolo/pyftpdlib) — FTP server library
- [Flask](https://flask.palletsprojects.com/) — Web framework
- [PyInstaller](https://pyinstaller.org/) — Packaging tool

## License

MIT
