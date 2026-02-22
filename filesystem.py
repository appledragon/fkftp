"""
MultiDirFilesystem - Virtual filesystem supporting multi-drive, multi-directory mapping.

Each user has a directory mapping dict. FTP clients see mount point names
under the virtual root /, with each mount point mapped to a real physical
path (which can span different drives).

Example::

  directories = {"projects": "D:\\\\Projects", "docs": "C:\\\\Docs"}
  FTP view: /projects/foo.txt  ->  D:\\\\Projects\\\\foo.txt
            /docs/readme.md    ->  C:\\\\Docs\\\\readme.md
"""

import os
import stat
import time

from pyftpdlib.filesystems import AbstractedFS

# Global user directory mapping, populated by server.py at startup
# Format: { "username": { "mount_name": "real_path", ... }, ... }
USER_DIR_MAP = {}


class _VirtualDirStat:
    """Synthetic stat result for virtual directories (root/mount points)."""

    def __init__(self):
        self.st_mode = stat.S_IFDIR | 0o755
        self.st_ino = 0
        self.st_dev = 0
        self.st_nlink = 2
        self.st_uid = 0
        self.st_gid = 0
        self.st_size = 0
        t = time.time()
        self.st_atime = t
        self.st_mtime = t
        self.st_ctime = t


class MultiDirFilesystem(AbstractedFS):
    """Virtual filesystem supporting multi-directory mapping.

    Virtual path structure:
      /                     -> Virtual root (synthetic directory listing all mount points)
      /mount_name/          -> Root of the corresponding physical path
      /mount_name/sub/path  -> Sub-path under the corresponding physical path
    """

    def __init__(self, root, cmd_channel):
        super().__init__(root, cmd_channel)
        username = cmd_channel.username
        self._dir_map = USER_DIR_MAP.get(username, {})
        # Normalize all physical paths
        self._dir_map = {
            name: os.path.normpath(path)
            for name, path in self._dir_map.items()
        }

    def _find_mount(self, name):
        """Case-insensitive mount point name lookup."""
        name_lower = name.lower()
        for mount_name in self._dir_map:
            if mount_name.lower() == name_lower:
                return mount_name
        return None

    def _resolve(self, ftppath):
        """Resolve virtual FTP path to (mount_name, relative_parts) or (None, [])."""
        normed = self.ftpnorm(ftppath)
        parts = [p for p in normed.split("/") if p]
        if not parts:
            return None, []
        mount_name = self._find_mount(parts[0])
        if mount_name is None:
            return parts[0], parts[1:]  # Return name but not in mapping
        return mount_name, parts[1:]

    def _is_virtual_root(self, ftppath):
        """Check if path is the virtual root /."""
        return self.ftpnorm(ftppath) == "/"

    def _to_absolute_ftppath(self, ftppath):
        """Convert a possibly relative FTP path to an absolute path (starting with /)."""
        import posixpath
        normed = self.ftpnorm(ftppath)
        if not normed.startswith("/"):
            normed = posixpath.normpath(self.cwd + "/" + normed)
        return normed

    def ftp2fs(self, ftppath):
        """Virtual FTP path -> real filesystem path."""
        ftppath = self._to_absolute_ftppath(ftppath)
        normed = self.ftpnorm(ftppath)
        if normed == "/":
            return normed  # Virtual root has no real path

        mount_name, sub_parts = self._resolve(ftppath)
        if mount_name in self._dir_map:
            real_base = self._dir_map[mount_name]
            if sub_parts:
                return os.path.normpath(os.path.join(real_base, *sub_parts))
            return real_base
        # Mount point does not exist; return a nonexistent path
        return os.path.normpath(os.path.join("__invalid__", mount_name))

    def fs2ftp(self, fspath):
        """Real filesystem path -> virtual FTP path."""
        fspath = os.path.normpath(fspath)
        # Find best match among all mount points
        for mount_name, real_base in self._dir_map.items():
            real_base_norm = os.path.normpath(real_base)
            # Check if fspath is under real_base
            if os.path.normcase(fspath) == os.path.normcase(real_base_norm):
                return "/" + mount_name
            if os.path.normcase(fspath).startswith(
                os.path.normcase(real_base_norm) + os.sep
            ):
                rel = fspath[len(real_base_norm):].lstrip(os.sep)
                return "/" + mount_name + "/" + rel.replace(os.sep, "/")
        return "/"

    def validpath(self, path):
        """Check if path is valid — must be under a mount directory or the virtual root."""
        if path == "/":
            return True
        path = os.path.normpath(path)
        for real_base in self._dir_map.values():
            real_base = os.path.normpath(real_base)
            if os.path.normcase(path) == os.path.normcase(real_base):
                return True
            if os.path.normcase(path).startswith(
                os.path.normcase(real_base) + os.sep
            ):
                return True
        return False

    def chdir(self, path):
        """Change current working directory."""
        if path == "/" or self._is_virtual_path(path):
            self.cwd = self.fs2ftp(path) if path != "/" else "/"
        else:
            self.cwd = self.fs2ftp(path)

    def _is_virtual_path(self, fspath):
        """Check if path is the virtual root or a mount point root."""
        if fspath == "/":
            return True
        fspath = os.path.normpath(fspath)
        for real_base in self._dir_map.values():
            if os.path.normcase(fspath) == os.path.normcase(
                os.path.normpath(real_base)
            ):
                return True
        return False

    def isdir(self, path):
        if path == "/":
            return True
        # Check if path is a mount point root
        path_norm = os.path.normpath(path) if path != "/" else path
        for real_base in self._dir_map.values():
            if os.path.normcase(path_norm) == os.path.normcase(
                os.path.normpath(real_base)
            ):
                return True
        return os.path.isdir(path)

    def isfile(self, path):
        if path == "/":
            return False
        return os.path.isfile(path)

    def lexists(self, path):
        if path == "/":
            return True
        return os.path.lexists(path)

    def listdir(self, path):
        if path == "/":
            return sorted(self._dir_map.keys())
        return os.listdir(path)

    def listdirinfo(self, path):
        return self.listdir(path)

    def stat(self, path):
        if path == "/":
            return _VirtualDirStat()
        return os.stat(path)

    def lstat(self, path):
        if path == "/":
            return _VirtualDirStat()
        return os.lstat(path)

    def getsize(self, path):
        if path == "/":
            return 0
        return os.path.getsize(path)

    def getmtime(self, path):
        if path == "/":
            return time.time()
        return os.path.getmtime(path)

    def realpath(self, path):
        if path == "/":
            return path
        return os.path.realpath(path)

    def mkdir(self, path):
        os.mkdir(path)

    def rmdir(self, path):
        # Prevent deletion of mount point root directories
        path_norm = os.path.normpath(path)
        for real_base in self._dir_map.values():
            if os.path.normcase(path_norm) == os.path.normcase(
                os.path.normpath(real_base)
            ):
                from pyftpdlib.exceptions import FilesystemError
                raise FilesystemError("Cannot remove a mount point.")
        os.rmdir(path)

    def format_list(self, basedir, listing, ignore_err=True):
        """List directory, handling the virtual root case."""
        if basedir == "/":
            # Virtual root: list mount points
            for name in listing:
                if name in self._dir_map:
                    real_path = self._dir_map[name]
                    try:
                        st = os.stat(real_path)
                        mtime = time.localtime(st.st_mtime)
                    except OSError:
                        st = _VirtualDirStat()
                        mtime = time.localtime()
                    from pyftpdlib.filesystems import _months_map
                    mtimestr = "%s %s" % (
                        _months_map[mtime.tm_mon],
                        time.strftime("%d %H:%M", mtime),
                    )
                    line = "drwxrwxrwx   1 owner   group   %8s %s %s\r\n" % (
                        st.st_size,
                        mtimestr,
                        name,
                    )
                    yield line.encode(
                        self.cmd_channel.encoding,
                        self.cmd_channel.unicode_errors,
                    )
            return
        yield from super().format_list(basedir, listing, ignore_err)

    def format_mlsx(self, basedir, listing, perms, facts, ignore_err=True):
        """MLSD directory listing, handling the virtual root case."""
        if basedir == "/":
            for name in listing:
                if name in self._dir_map:
                    real_path = self._dir_map[name]
                    try:
                        st = os.stat(real_path)
                    except OSError:
                        st = _VirtualDirStat()

                    if self.cmd_channel.use_gmt_times:
                        timefunc = time.gmtime
                    else:
                        timefunc = time.localtime

                    retfacts = {}
                    if "type" in facts:
                        retfacts["type"] = "dir"
                    if "perm" in facts:
                        permdir = "".join(
                            [x for x in perms if x not in "arw"]
                        )
                        if ("w" in perms) or ("a" in perms) or ("f" in perms):
                            permdir += "c"
                        if "d" in perms:
                            permdir += "p"
                        retfacts["perm"] = permdir
                    if "size" in facts:
                        retfacts["size"] = st.st_size
                    if "modify" in facts:
                        try:
                            retfacts["modify"] = time.strftime(
                                "%Y%m%d%H%M%S", timefunc(st.st_mtime)
                            )
                        except ValueError:
                            pass
                    if "create" in facts:
                        try:
                            retfacts["create"] = time.strftime(
                                "%Y%m%d%H%M%S", timefunc(st.st_ctime)
                            )
                        except ValueError:
                            pass

                    factstring = "".join(
                        [
                            f"{x}={retfacts[x]};"
                            for x in sorted(retfacts.keys())
                        ]
                    )
                    line = f"{factstring} {name}\r\n"
                    yield line.encode(
                        self.cmd_channel.encoding,
                        self.cmd_channel.unicode_errors,
                    )
            return
        yield from super().format_mlsx(
            basedir, listing, perms, facts, ignore_err
        )
