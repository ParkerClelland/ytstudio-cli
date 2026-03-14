# pyright: reportMissingImports=false, reportMissingTypeStubs=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownMemberType=false, reportUnknownVariableType=false
import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

import ytstudio.config as config_module
from ytstudio.main import app

runner = CliRunner()


@pytest.fixture
def temp_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CLIENT_SECRETS_FILE", tmp_path / "client_secrets.json")
    monkeypatch.setattr(config_module, "CREDENTIALS_FILE", tmp_path / "credentials.json")
    return tmp_path


def create_profile(name: str) -> None:
    config_module.ensure_profile_dir(name)


class TestChannelList:
    def test_list_no_profiles(self, temp_config):
        _ = temp_config
        result = runner.invoke(app, ["channel", "list"])

        assert result.exit_code == 0
        assert "No channel profiles configured" in result.stdout

    def test_list_profiles_with_active_indicator(self, temp_config):
        _ = temp_config
        create_profile("alpha")
        create_profile("beta")
        config_module.set_active_profile("beta")

        result = runner.invoke(app, ["channel", "list"])

        assert result.exit_code == 0
        assert "Profile" in result.stdout
        assert "Active" in result.stdout
        assert "alpha" in result.stdout
        assert "beta" in result.stdout
        assert "\u2713" in result.stdout

    def test_list_json_output(self, temp_config):
        _ = temp_config
        create_profile("alpha")
        create_profile("beta")
        config_module.set_active_profile("beta")

        result = runner.invoke(app, ["channel", "list", "--json"])

        assert result.exit_code == 0
        assert json.loads(result.stdout) == [
            {"name": "alpha", "active": False},
            {"name": "beta", "active": True},
        ]


class TestChannelStatus:
    def test_status_no_profiles(self, temp_config):
        _ = temp_config
        result = runner.invoke(app, ["channel", "status"])

        assert result.exit_code == 1
        assert "No channel profiles configured" in result.stdout

    def test_status_profiles_exist(self, temp_config, mock_auth):
        assert mock_auth is not None
        _ = temp_config
        create_profile("main")
        config_module.set_active_profile("main")

        result = runner.invoke(app, ["channel", "status"])

        assert result.exit_code == 0
        assert "Profile" in result.stdout
        assert "main" in result.stdout
        assert "Channel" in result.stdout
        assert "Test Channel" in result.stdout
        assert "Subscribers" in result.stdout
        assert "125000" in result.stdout
        assert "Videos" in result.stdout
        assert "50" in result.stdout
        mock_auth.channels.return_value.list.assert_called_once_with(
            part="snippet,statistics",
            mine=True,
        )

    def test_status_no_channel_found_for_active_profile(self, temp_config, mock_auth):
        _ = temp_config
        create_profile("main")
        config_module.set_active_profile("main")
        mock_auth.channels.return_value.list.return_value.execute.return_value = {"items": []}

        result = runner.invoke(app, ["channel", "status"])

        assert result.exit_code == 1
        assert "No channel found for the active profile" in result.stdout


class TestChannelAdd:
    def test_add_valid_name_creates_dir_and_authenticates(self, temp_config):
        with (
            patch("ytstudio.commands.channel.is_demo_mode", return_value=False),
            patch("ytstudio.commands.channel.authenticate") as mock_authenticate,
        ):
            result = runner.invoke(app, ["channel", "add", "primary"])

        assert result.exit_code == 0
        assert (temp_config / "profiles" / "primary").is_dir()
        assert "Channel added as profile 'primary'" in result.stdout
        mock_authenticate.assert_called_once_with(profile="primary")

    def test_add_invalid_name_returns_error(self, temp_config):
        result = runner.invoke(app, ["channel", "add", "bad name!"])

        assert result.exit_code != 0
        assert "invalid" in result.output.lower()
        assert not (temp_config / "profiles" / "bad name!").exists()

    def test_add_duplicate_name_errors(self, temp_config):
        _ = temp_config
        create_profile("primary")

        result = runner.invoke(app, ["channel", "add", "primary"])

        assert result.exit_code == 1
        assert "already exists" in result.stdout

    def test_add_demo_mode_skips_authentication(self, temp_config):
        with (
            patch("ytstudio.commands.channel.is_demo_mode", return_value=True),
            patch("ytstudio.commands.channel.authenticate") as mock_authenticate,
        ):
            result = runner.invoke(app, ["channel", "add", "demo"])

        assert result.exit_code == 0
        assert (temp_config / "profiles" / "demo").is_dir()
        assert "Channel added as profile 'demo'" in result.stdout
        mock_authenticate.assert_not_called()

    def test_add_authentication_failure_removes_profile_dir(self, temp_config):
        with (
            patch("ytstudio.commands.channel.is_demo_mode", return_value=False),
            patch(
                "ytstudio.commands.channel.authenticate",
                side_effect=RuntimeError("boom"),
            ),
        ):
            result = runner.invoke(app, ["channel", "add", "broken"])

        assert result.exit_code == 1
        assert "Failed to authenticate profile 'broken': boom" in result.stdout
        assert not (temp_config / "profiles" / "broken").exists()


class TestChannelUse:
    def test_use_valid_profile_switches_active(self, temp_config):
        _ = temp_config
        create_profile("alpha")
        create_profile("beta")
        config_module.set_active_profile("alpha")

        result = runner.invoke(app, ["channel", "use", "beta"])

        assert result.exit_code == 0
        assert config_module.get_active_profile() == "beta"
        assert "Switched to profile 'beta'" in result.stdout

    def test_use_nonexistent_profile_lists_available_profiles(self, temp_config):
        _ = temp_config
        create_profile("alpha")
        create_profile("beta")

        result = runner.invoke(app, ["channel", "use", "gamma"])

        assert result.exit_code == 1
        assert "Profile 'gamma' not found" in result.stdout
        assert "Available profiles: alpha, beta" in result.stdout

    def test_use_invalid_name_returns_error(self, temp_config):
        _ = temp_config
        result = runner.invoke(app, ["channel", "use", "bad name!"])

        assert result.exit_code != 0
        assert "invalid" in result.output.lower()


class TestChannelRemove:
    def test_remove_inactive_profile_with_confirmation(self, temp_config):
        create_profile("alpha")
        create_profile("beta")
        config_module.set_active_profile("alpha")

        result = runner.invoke(app, ["channel", "remove", "beta"], input="y\n")

        assert result.exit_code == 0
        assert not (temp_config / "profiles" / "beta").exists()
        assert "Removed profile 'beta'" in result.stdout

    def test_remove_active_profile_errors(self, temp_config):
        create_profile("alpha")
        config_module.set_active_profile("alpha")

        result = runner.invoke(app, ["channel", "remove", "alpha"])

        assert result.exit_code == 1
        assert "Cannot remove active profile 'alpha'" in result.stdout
        assert (temp_config / "profiles" / "alpha").exists()

    def test_remove_nonexistent_profile_errors(self, temp_config):
        _ = temp_config
        result = runner.invoke(app, ["channel", "remove", "missing"])

        assert result.exit_code == 1
        assert "Profile 'missing' not found" in result.stdout

    def test_remove_decline_confirmation_aborts(self, temp_config):
        create_profile("alpha")
        create_profile("beta")
        config_module.set_active_profile("alpha")

        result = runner.invoke(app, ["channel", "remove", "beta"], input="n\n")

        assert result.exit_code != 0
        assert (temp_config / "profiles" / "beta").exists()
        assert "Remove profile 'beta' and its credentials?" in result.stdout

    def test_remove_invalid_name_returns_error(self, temp_config):
        _ = temp_config
        result = runner.invoke(app, ["channel", "remove", "bad name!"])

        assert result.exit_code != 0
        assert "invalid" in result.output.lower()
