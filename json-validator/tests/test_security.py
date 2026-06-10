import pytest
from json_validator.security import check_path, PathError


class TestCheckPath:
    def test_traversal_dotdot_rejected(self, tmp_path):
        bad = str(tmp_path / ".." / "etc" / "passwd")
        with pytest.raises(PathError, match="Disallowed path"):
            check_path(bad)

    def test_plain_relative_path_accepted(self, tmp_path):
        good = str(tmp_path / "data.json")
        # Should not raise — path stays within tmp_path parent
        check_path(good)  # no exception expected

    def test_absolute_safe_path_accepted(self, tmp_path):
        good = str(tmp_path / "schema.json")
        check_path(good)

    def test_double_dotdot_in_middle_rejected(self, tmp_path):
        bad = str(tmp_path / "subdir" / ".." / ".." / "secret")
        with pytest.raises(PathError):
            check_path(bad)

    def test_unc_path_rejected(self, tmp_path):
        with pytest.raises(PathError, match="Disallowed path"):
            check_path(r"\\server\share\file.json")

    def test_unix_double_slash_rejected(self, tmp_path):
        with pytest.raises(PathError, match="Disallowed path"):
            check_path("//server/share/file.json")
