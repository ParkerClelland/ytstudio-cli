import json
from unittest.mock import patch

import pytest
import typer

from ytstudio import config


@pytest.fixture
def temp_config(tmp_path):
    config_dir = tmp_path / ".config" / "ytstudio-cli"
    config_dir.mkdir(parents=True)

    with (
        patch.object(config, "CONFIG_DIR", config_dir),
        patch.object(config, "CLIENT_SECRETS_FILE", config_dir / "client_secrets.json"),
        patch.object(config, "CREDENTIALS_FILE", config_dir / "credentials.json"),
    ):
        yield config_dir


class TestCredentials:
    def test_save_and_load(self, temp_config):
        creds = {"token": "test_token"}
        config.save_credentials(creds)
        assert config.load_credentials() == creds

    def test_load_returns_none_when_missing(self, temp_config):
        assert config.load_credentials() is None

    def test_clear(self, temp_config):
        config.save_credentials({"token": "test"})
        config.clear_credentials()
        assert config.load_credentials() is None


class TestSetupCredentials:
    def test_setup_with_file(self, temp_config, tmp_path):
        source = tmp_path / "secrets.json"
        source.write_text('{"installed": {"client_id": "test"}}')

        config.setup_credentials(str(source))
        secrets = config.get_client_secrets()
        assert secrets is not None
        assert secrets["installed"]["client_id"] == "test"

    def test_setup_with_missing_file(self, temp_config):
        with pytest.raises(SystemExit):
            config.setup_credentials("/nonexistent/file.json")


class TestProfileFunctions:
    def test_validate_profile_name_valid(self, temp_config):
        assert config.validate_profile_name("my-channel") == "my-channel"
        assert config.validate_profile_name("SanctifiedChurch") == "SanctifiedChurch"
        assert config.validate_profile_name("channel_123") == "channel_123"

    def test_validate_profile_name_invalid(self, temp_config):
        with pytest.raises(typer.BadParameter):
            config.validate_profile_name("bad name!")
        with pytest.raises(typer.BadParameter):
            config.validate_profile_name("bad/name")
        with pytest.raises(typer.BadParameter):
            config.validate_profile_name("")

    def test_get_active_profile_default(self, temp_config):
        # No config.json -> returns "default"
        assert config.get_active_profile() == "default"

    def test_set_and_get_active_profile(self, temp_config):
        config.set_active_profile("SanctifiedChurch")
        assert config.get_active_profile() == "SanctifiedChurch"

    def test_get_profile_dir(self, temp_config):
        d = config.get_profile_dir("my-channel")
        assert d == temp_config / "profiles" / "my-channel"

    def test_get_profile_credentials_path(self, temp_config):
        p = config.get_profile_credentials_path("my-channel")
        assert p == temp_config / "profiles" / "my-channel" / "credentials.json"

    def test_ensure_profile_dir(self, temp_config):
        config.ensure_profile_dir("test-profile")
        assert (temp_config / "profiles" / "test-profile").is_dir()

    def test_list_profiles_empty(self, temp_config):
        assert config.list_profiles() == []

    def test_list_profiles_sorted(self, temp_config):
        config.ensure_profile_dir("ZChannel")
        config.ensure_profile_dir("AChannel")
        config.ensure_profile_dir("MChannel")
        assert config.list_profiles() == ["AChannel", "MChannel", "ZChannel"]


class TestProfileCredentials:
    def test_save_to_named_profile(self, temp_config):
        creds = {"token": "test_token"}
        config.save_credentials(creds, profile="my-profile")
        path = temp_config / "profiles" / "my-profile" / "credentials.json"
        assert path.exists()
        assert json.loads(path.read_text()) == creds

    def test_load_from_active_profile(self, temp_config):
        config.ensure_profile_dir("active-ch")
        config.set_active_profile("active-ch")
        creds = {"token": "profile_token"}
        config.save_credentials(creds, profile="active-ch")
        assert config.load_credentials() == creds

    def test_legacy_fallback(self, temp_config):
        # credentials.json at root (no profiles dir) -> load_credentials returns it
        creds = {"token": "legacy_token"}
        (temp_config / "credentials.json").write_text(json.dumps(creds))
        assert config.load_credentials() == creds

    def test_profile_path_takes_precedence_over_legacy(self, temp_config):
        # Both profile path AND legacy exist -> profile takes precedence
        config.ensure_profile_dir("default")
        config.set_active_profile("default")
        profile_creds = {"token": "profile_token"}
        legacy_creds = {"token": "legacy_token"}
        config.save_credentials(profile_creds, profile="default")
        (temp_config / "credentials.json").write_text(json.dumps(legacy_creds))
        assert config.load_credentials() == profile_creds


class TestMigration:
    def test_existing_user_migrated_to_default(self, temp_config):
        """Existing credentials.json gets migrated to profiles/default/."""
        creds = {"token": "old_token"}
        (temp_config / "credentials.json").write_text(json.dumps(creds))

        result = config.load_credentials()

        assert result == creds
        assert not (temp_config / "credentials.json").exists()
        assert (temp_config / "profiles" / "default" / "credentials.json").exists()
        config_data = json.loads((temp_config / "config.json").read_text())
        assert config_data["active_profile"] == "default"

    def test_already_migrated_is_noop(self, temp_config):
        """If profiles/ exists, migration does not run."""
        config.ensure_profile_dir("existing-profile")
        creds = {"token": "new_token"}
        config.save_credentials(creds, profile="existing-profile")
        config.set_active_profile("existing-profile")

        config.maybe_migrate()

        assert (temp_config / "profiles" / "existing-profile" / "credentials.json").exists()

    def test_brand_new_user_is_noop(self, temp_config):
        """No credentials.json and no profiles/ means migration is a no-op."""
        config.maybe_migrate()

        assert not (temp_config / "profiles").exists()
        assert not (temp_config / "config.json").exists()

    def test_migration_idempotent_after_partial(self, temp_config):
        """Existing profiles/ with legacy file keeps migration as no-op."""
        creds = {"token": "partial_token"}
        (temp_config / "credentials.json").write_text(json.dumps(creds))

        (temp_config / "profiles").mkdir(parents=True, exist_ok=True)

        config.maybe_migrate()

        assert (temp_config / "credentials.json").exists()
