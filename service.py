"""FKFTP Windows Service — Register FKFTP as a Windows service for auto-start on boot."""

import logging
import os
import sys
import subprocess

logger = logging.getLogger("fkftp")

SERVICE_NAME = "FKFTPServer"
SERVICE_DISPLAY = "FKFTP Server"
SERVICE_DESC = "FKFTP - Multi-directory FTP Server with Web Management"


def _get_exe_path():
    """Get current executable path."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(sys.argv[0])


def install_service():
    """Install Windows service."""
    exe = _get_exe_path()
    # Use sc.exe to create service, binPath points to fkftp.exe --run-service
    bin_path = f'"{exe}" --run-service'
    cmds = [
        ["sc", "create", SERVICE_NAME,
         f"binPath={bin_path}",
         "start=auto",
         f"DisplayName={SERVICE_DISPLAY}"],
        ["sc", "description", SERVICE_NAME, SERVICE_DESC],
    ]
    for cmd in cmds:
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0:
            msg = r.stderr.decode(errors="replace").strip() or r.stdout.decode(errors="replace").strip()
            print(f"Error: {msg}")
            return False
        print(r.stdout.decode(errors="replace").strip())
    print(f"Service '{SERVICE_NAME}' installed successfully.")
    print("Use 'fkftp.exe --service start' or 'net start FKFTPServer' to start.")
    return True


def uninstall_service():
    """Uninstall Windows service."""
    # Try to stop first
    subprocess.run(["sc", "stop", SERVICE_NAME],
                   capture_output=True)
    r = subprocess.run(["sc", "delete", SERVICE_NAME],
                       capture_output=True)
    if r.returncode != 0:
        msg = r.stderr.decode(errors="replace").strip() or r.stdout.decode(errors="replace").strip()
        print(f"Error: {msg}")
        return False
    print(f"Service '{SERVICE_NAME}' uninstalled.")
    return True


def start_service():
    """Start the service."""
    r = subprocess.run(["sc", "start", SERVICE_NAME],
                       capture_output=True)
    msg = r.stdout.decode(errors="replace").strip() or r.stderr.decode(errors="replace").strip()
    print(msg)
    return r.returncode == 0


def stop_service():
    """Stop the service."""
    r = subprocess.run(["sc", "stop", SERVICE_NAME],
                       capture_output=True)
    msg = r.stdout.decode(errors="replace").strip() or r.stderr.decode(errors="replace").strip()
    print(msg)
    return r.returncode == 0


def query_service():
    """Query service status and return status string."""
    r = subprocess.run(["sc", "query", SERVICE_NAME],
                       capture_output=True)
    output = r.stdout.decode(errors="replace")
    if "RUNNING" in output:
        return "running"
    if "STOPPED" in output:
        return "stopped"
    if "PENDING" in output:
        return "pending"
    return "not_installed"


def run_as_service():
    """Run as a Windows Service (called by SCM)."""
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil

    class FKFTPService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY
        _svc_description_ = SERVICE_DESC

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self.stop_event = win32event.CreateEvent(None, 0, 0, None)
            self._ftp_server = None
            self._flask_thread = None

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self.stop_event)
            # Stop FTP server
            if self._ftp_server:
                try:
                    self._ftp_server.close_all()
                except Exception:
                    pass
            # Flask thread is daemon, will exit automatically

        def SvcDoRun(self):
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, ""),
            )
            self.main()

        def main(self):
            import json
            import threading
            from server import setup_server, load_config
            from filesystem import USER_DIR_MAP

            # Determine config directory
            if getattr(sys, "frozen", False):
                config_dir = os.path.dirname(sys.executable)
            else:
                config_dir = os.path.dirname(os.path.abspath(__file__))

            config_path = os.path.join(config_dir, "config.json")

            # Set up logging
            log_path = os.path.join(config_dir, "fkftp_service.log")
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
                handlers=[
                    logging.FileHandler(log_path, encoding="utf-8"),
                ],
            )
            svc_logger = logging.getLogger("fkftp")

            try:
                config = load_config(config_path)
            except Exception as e:
                svc_logger.error("Failed to load config: %s", e)
                return

            # Start FTP server
            if config.get("users"):
                try:
                    USER_DIR_MAP.clear()
                    self._ftp_server = setup_server(config)
                    ftp_thread = threading.Thread(
                        target=self._ftp_server.serve_forever, daemon=True
                    )
                    ftp_thread.start()
                    svc_logger.info(
                        "FTP server started on port %d",
                        config.get("port", 2121),
                    )
                except Exception as e:
                    svc_logger.exception("Failed to start FTP server")

            # Start Flask web management (optional)
            try:
                from app import app as flask_app
                web_port = config.get("web_port", 8080)
                self._flask_thread = threading.Thread(
                    target=lambda: flask_app.run(
                        host="127.0.0.1",
                        port=web_port,
                        debug=False,
                        use_reloader=False,
                    ),
                    daemon=True,
                )
                self._flask_thread.start()
                svc_logger.info("Web management on port %d", web_port)
            except Exception as e:
                svc_logger.exception("Failed to start web management")

            # Wait for stop signal
            win32event.WaitForSingleObject(
                self.stop_event, win32event.INFINITE
            )
            svc_logger.info("Service stopped.")

    # Register service class with SCM and start dispatcher
    servicemanager.Initialize()
    servicemanager.PrepareToHostSingle(FKFTPService)
    servicemanager.StartServiceCtrlDispatcher()
