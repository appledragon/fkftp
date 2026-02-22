"""Tests for MultiDirFilesystem virtual filesystem."""

import os
import stat
import tempfile
import time

import pytest
from unittest.mock import MagicMock

from filesystem import MultiDirFilesystem, _VirtualDirStat, USER_DIR_MAP


def _make_fs(dir_map, username="testuser"):
    """Create a MultiDirFilesystem instance with mocked cmd_channel."""
    USER_DIR_MAP.clear()
    USER_DIR_MAP[username] = dir_map

    cmd_channel = MagicMock()
    cmd_channel.username = username
    cmd_channel.encoding = "utf-8"
    cmd_channel.unicode_errors = "replace"

    # Use a temp dir as root (required by AbstractedFS constructor)
    home = next(iter(dir_map.values()), os.path.normpath("."))
    fs = MultiDirFilesystem(home, cmd_channel)
    fs.cwd = "/"
    return fs


class TestVirtualDirStat:
    def test_is_directory(self):
        s = _VirtualDirStat()
        assert stat.S_ISDIR(s.st_mode)

    def test_has_zero_size(self):
        s = _VirtualDirStat()
        assert s.st_size == 0

    def test_has_recent_times(self):
        before = time.time() - 1
        s = _VirtualDirStat()
        after = time.time() + 1
        assert before < s.st_mtime < after


class TestMultiDirFilesystem:
    def test_listdir_virtual_root(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            fs = _make_fs({"alpha": d1, "beta": d2})
            result = fs.listdir("/")
            assert sorted(result) == ["alpha", "beta"]

    def test_isdir_virtual_root(self):
        fs = _make_fs({"m": tempfile.mkdtemp()})
        assert fs.isdir("/")

    def test_isfile_virtual_root(self):
        fs = _make_fs({"m": tempfile.mkdtemp()})
        assert not fs.isfile("/")

    def test_stat_virtual_root(self):
        fs = _make_fs({"m": tempfile.mkdtemp()})
        s = fs.stat("/")
        assert stat.S_ISDIR(s.st_mode)

    def test_getsize_virtual_root(self):
        fs = _make_fs({"m": tempfile.mkdtemp()})
        assert fs.getsize("/") == 0

    def test_ftp2fs_root(self):
        with tempfile.TemporaryDirectory() as d:
            fs = _make_fs({"docs": d})
            assert fs.ftp2fs("/") == "/"

    def test_ftp2fs_mount_point(self):
        with tempfile.TemporaryDirectory() as d:
            fs = _make_fs({"docs": d})
            result = fs.ftp2fs("/docs")
            assert os.path.normpath(result) == os.path.normpath(d)

    def test_ftp2fs_subpath(self):
        with tempfile.TemporaryDirectory() as d:
            fs = _make_fs({"docs": d})
            result = fs.ftp2fs("/docs/sub/file.txt")
            expected = os.path.normpath(os.path.join(d, "sub", "file.txt"))
            assert os.path.normpath(result) == expected

    def test_ftp2fs_nonexistent_mount(self):
        with tempfile.TemporaryDirectory() as d:
            fs = _make_fs({"docs": d})
            result = fs.ftp2fs("/nosuch")
            # Returns a path with __invalid__
            assert "__invalid__" in result

    def test_fs2ftp_mount_root(self):
        with tempfile.TemporaryDirectory() as d:
            fs = _make_fs({"docs": d})
            result = fs.fs2ftp(d)
            assert result == "/docs"

    def test_fs2ftp_subpath(self):
        with tempfile.TemporaryDirectory() as d:
            fs = _make_fs({"docs": d})
            subpath = os.path.join(d, "a", "b.txt")
            result = fs.fs2ftp(subpath)
            assert result == "/docs/a/b.txt"

    def test_fs2ftp_unknown_path(self):
        with tempfile.TemporaryDirectory() as d:
            fs = _make_fs({"docs": d})
            result = fs.fs2ftp("/some/random/path")
            assert result == "/"

    def test_validpath_root(self):
        with tempfile.TemporaryDirectory() as d:
            fs = _make_fs({"docs": d})
            assert fs.validpath("/")

    def test_validpath_mount_root(self):
        with tempfile.TemporaryDirectory() as d:
            fs = _make_fs({"docs": d})
            assert fs.validpath(d)

    def test_validpath_under_mount(self):
        with tempfile.TemporaryDirectory() as d:
            fs = _make_fs({"docs": d})
            assert fs.validpath(os.path.join(d, "subdir"))

    def test_validpath_outside_mount(self):
        with tempfile.TemporaryDirectory() as d:
            fs = _make_fs({"docs": d})
            assert not fs.validpath("/some/random/path")

    def test_isdir_mount_point(self):
        with tempfile.TemporaryDirectory() as d:
            fs = _make_fs({"docs": d})
            assert fs.isdir(d)

    def test_listdir_real_dir(self):
        with tempfile.TemporaryDirectory() as d:
            # Create some files
            open(os.path.join(d, "a.txt"), "w").close()
            open(os.path.join(d, "b.txt"), "w").close()
            fs = _make_fs({"docs": d})
            result = fs.listdir(d)
            assert sorted(result) == ["a.txt", "b.txt"]

    def test_lexists_root(self):
        with tempfile.TemporaryDirectory() as d:
            fs = _make_fs({"docs": d})
            assert fs.lexists("/")

    def test_realpath_root(self):
        with tempfile.TemporaryDirectory() as d:
            fs = _make_fs({"docs": d})
            assert fs.realpath("/") == "/"

    def test_mkdir(self):
        with tempfile.TemporaryDirectory() as d:
            fs = _make_fs({"docs": d})
            new_dir = os.path.join(d, "newdir")
            fs.mkdir(new_dir)
            assert os.path.isdir(new_dir)

    def test_rmdir_nonempty_raises(self):
        with tempfile.TemporaryDirectory() as d:
            fs = _make_fs({"docs": d})
            sub = os.path.join(d, "subdir")
            os.mkdir(sub)
            open(os.path.join(sub, "file.txt"), "w").close()
            with pytest.raises(OSError):
                fs.rmdir(sub)

    def test_rmdir_normal(self):
        with tempfile.TemporaryDirectory() as d:
            fs = _make_fs({"docs": d})
            sub = os.path.join(d, "subdir")
            os.mkdir(sub)
            fs.rmdir(sub)
            assert not os.path.exists(sub)

    def test_rmdir_mount_root_raises(self):
        with tempfile.TemporaryDirectory() as d:
            fs = _make_fs({"docs": d})
            with pytest.raises(Exception, match="mount point"):
                fs.rmdir(d)

    def test_find_mount_case_insensitive(self):
        with tempfile.TemporaryDirectory() as d:
            fs = _make_fs({"MyDocs": d})
            assert fs._find_mount("mydocs") == "MyDocs"
            assert fs._find_mount("MYDOCS") == "MyDocs"
            assert fs._find_mount("MyDocs") == "MyDocs"

    def test_find_mount_not_found(self):
        with tempfile.TemporaryDirectory() as d:
            fs = _make_fs({"docs": d})
            assert fs._find_mount("nosuch") is None

    def test_chdir_root(self):
        with tempfile.TemporaryDirectory() as d:
            fs = _make_fs({"docs": d})
            fs.chdir("/")
            assert fs.cwd == "/"

    def test_chdir_mount(self):
        with tempfile.TemporaryDirectory() as d:
            fs = _make_fs({"docs": d})
            fs.chdir(d)
            assert fs.cwd == "/docs"

    def test_multiple_mounts(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            fs = _make_fs({"projects": d1, "backup": d2})
            assert fs.ftp2fs("/projects") == os.path.normpath(d1)
            assert fs.ftp2fs("/backup") == os.path.normpath(d2)
            assert fs.validpath(d1)
            assert fs.validpath(d2)
