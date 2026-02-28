"""Tests for the security module (secrets manager and OAuth providers)."""

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
from cryptography.fernet import Fernet

from src.security.secrets_manager import SecretsManager, get_secrets_manager, reset_secrets_manager
from src.security.oauth_providers import (
    OAuthConfig,
    OAuthTokens,
    OAuthProvider,
    SpotifyOAuthProvider,
    get_oauth_provider,
    list_oauth_providers,
    register_oauth_provider,
)


class TestSecretsManager:
    """Tests for SecretsManager encryption and storage."""
    
    def test_init_with_explicit_key(self):
        """Test initialization with explicit master key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_file = Path(tmpdir) / "secrets.enc"
            master_key = Fernet.generate_key().decode('utf-8')
            
            manager = SecretsManager(secrets_file=secrets_file, master_key=master_key)
            
            assert manager.secrets_file == secrets_file
            assert manager._fernet is not None
    
    def test_init_with_env_var(self):
        """Test initialization with master key from environment."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_file = Path(tmpdir) / "secrets.enc"
            master_key = Fernet.generate_key().decode('utf-8')
            
            with patch.dict(os.environ, {"FIESTABOARD_MASTER_KEY": master_key}):
                manager = SecretsManager(secrets_file=secrets_file)
                
                assert manager._fernet is not None
    
    def test_init_generates_key_if_missing(self):
        """Test auto-generation of master key if not provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_file = Path(tmpdir) / "secrets.enc"
            
            with patch.dict(os.environ, {}, clear=True):
                manager = SecretsManager(secrets_file=secrets_file)
                
                assert manager._fernet is not None
    
    def test_set_and_get_secret(self):
        """Test storing and retrieving a secret."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_file = Path(tmpdir) / "secrets.enc"
            master_key = Fernet.generate_key().decode('utf-8')
            
            manager = SecretsManager(secrets_file=secrets_file, master_key=master_key)
            manager.set_secret("test_namespace", "test_key", "test_value")
            
            value = manager.get_secret("test_namespace", "test_key")
            assert value == "test_value"
    
    def test_get_nonexistent_secret(self):
        """Test retrieving a secret that doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_file = Path(tmpdir) / "secrets.enc"
            master_key = Fernet.generate_key().decode('utf-8')
            
            manager = SecretsManager(secrets_file=secrets_file, master_key=master_key)
            
            value = manager.get_secret("nonexistent", "key")
            assert value is None
    
    def test_secrets_persist_to_disk(self):
        """Test that secrets are persisted to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_file = Path(tmpdir) / "secrets.enc"
            master_key = Fernet.generate_key().decode('utf-8')
            
            # Create manager and store secret
            manager1 = SecretsManager(secrets_file=secrets_file, master_key=master_key)
            manager1.set_secret("spotify", "access_token", "secret_token_123")
            
            # Create new manager with same key
            manager2 = SecretsManager(secrets_file=secrets_file, master_key=master_key)
            
            # Should load from disk
            value = manager2.get_secret("spotify", "access_token")
            assert value == "secret_token_123"
    
    def test_wrong_key_cannot_decrypt(self):
        """Test that wrong master key cannot decrypt secrets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_file = Path(tmpdir) / "secrets.enc"
            key1 = Fernet.generate_key().decode('utf-8')
            key2 = Fernet.generate_key().decode('utf-8')
            
            # Store with first key
            manager1 = SecretsManager(secrets_file=secrets_file, master_key=key1)
            manager1.set_secret("test", "key", "value")
            
            # Try to load with different key
            manager2 = SecretsManager(secrets_file=secrets_file, master_key=key2)
            
            # Should not have the secret (decryption failed)
            value = manager2.get_secret("test", "key")
            assert value is None
    
    def test_delete_secret_key(self):
        """Test deleting a specific secret key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_file = Path(tmpdir) / "secrets.enc"
            master_key = Fernet.generate_key().decode('utf-8')
            
            manager = SecretsManager(secrets_file=secrets_file, master_key=master_key)
            manager.set_secret("test", "key1", "value1")
            manager.set_secret("test", "key2", "value2")
            
            manager.delete_secret("test", "key1")
            
            assert manager.get_secret("test", "key1") is None
            assert manager.get_secret("test", "key2") == "value2"
    
    def test_delete_namespace(self):
        """Test deleting an entire namespace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_file = Path(tmpdir) / "secrets.enc"
            master_key = Fernet.generate_key().decode('utf-8')
            
            manager = SecretsManager(secrets_file=secrets_file, master_key=master_key)
            manager.set_secret("test", "key1", "value1")
            manager.set_secret("test", "key2", "value2")
            
            manager.delete_secret("test")
            
            assert manager.get_secret("test", "key1") is None
            assert manager.get_secret("test", "key2") is None
    
    def test_get_namespace(self):
        """Test retrieving all secrets in a namespace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_file = Path(tmpdir) / "secrets.enc"
            master_key = Fernet.generate_key().decode('utf-8')
            
            manager = SecretsManager(secrets_file=secrets_file, master_key=master_key)
            manager.set_secret("spotify", "access_token", "token1")
            manager.set_secret("spotify", "refresh_token", "token2")
            
            namespace = manager.get_namespace("spotify")
            
            assert namespace == {
                "access_token": "token1",
                "refresh_token": "token2"
            }
    
    def test_list_namespaces(self):
        """Test listing all namespaces."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_file = Path(tmpdir) / "secrets.enc"
            master_key = Fernet.generate_key().decode('utf-8')
            
            manager = SecretsManager(secrets_file=secrets_file, master_key=master_key)
            manager.set_secret("spotify", "token", "value1")
            manager.set_secret("google", "token", "value2")
            
            namespaces = manager.list_namespaces()
            
            assert set(namespaces) == {"spotify", "google"}
    
    def test_get_secrets_manager_singleton(self):
        """Test that get_secrets_manager returns singleton."""
        reset_secrets_manager()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_file = Path(tmpdir) / "secrets.enc"
            
            manager1 = get_secrets_manager(secrets_file=secrets_file)
            manager2 = get_secrets_manager()
            
            assert manager1 is manager2
        
        reset_secrets_manager()
    
    def test_auto_persist_master_key(self):
        """Test that master key is auto-persisted to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_file = Path(tmpdir) / "secrets.enc"
            key_file = Path(tmpdir) / "master.key"
            
            with patch('src.security.secrets_manager.DEFAULT_MASTER_KEY_FILE', key_file):
                with patch.dict(os.environ, {}, clear=True):
                    # First init - should generate and save key
                    manager1 = SecretsManager(secrets_file=secrets_file)
                    manager1.set_secret("test", "key", "value")
                    
                    # Key file should exist
                    assert key_file.exists()
                    saved_key = key_file.read_text().strip()
                    assert len(saved_key) > 0
                    
                    # Second init - should load from file
                    manager2 = SecretsManager(secrets_file=secrets_file)
                    
                    # Should be able to decrypt secrets from first manager
                    value = manager2.get_secret("test", "key")
                    assert value == "value"


class TestOAuthConfig:
    """Tests for OAuthConfig dataclass."""
    
    def test_oauth_config_creation(self):
        """Test creating an OAuth configuration."""
        config = OAuthConfig(
            client_id="test_client",
            client_secret="test_secret",
            redirect_uri="http://localhost/callback",
            scope="test_scope",
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token"
        )
        
        assert config.client_id == "test_client"
        assert config.client_secret == "test_secret"
        assert config.scope == "test_scope"


class TestOAuthTokens:
    """Tests for OAuthTokens dataclass."""
    
    def test_oauth_tokens_creation(self):
        """Test creating OAuth tokens."""
        tokens = OAuthTokens(
            access_token="access_123",
            refresh_token="refresh_456",
            expires_in=3600,
            token_type="Bearer",
            scope="test_scope"
        )
        
        assert tokens.access_token == "access_123"
        assert tokens.refresh_token == "refresh_456"
        assert tokens.expires_in == 3600
    
    def test_oauth_tokens_minimal(self):
        """Test creating OAuth tokens with only access_token."""
        tokens = OAuthTokens(access_token="access_only")
        
        assert tokens.access_token == "access_only"
        assert tokens.refresh_token is None
        assert tokens.expires_in is None


class TestSpotifyOAuthProvider:
    """Tests for Spotify OAuth provider."""
    
    def test_provider_id(self):
        """Test provider ID is 'spotify'."""
        provider = SpotifyOAuthProvider()
        assert provider.provider_id == "spotify"
    
    def test_provider_name(self):
        """Test provider name."""
        provider = SpotifyOAuthProvider()
        assert provider.provider_name == "Spotify"
    
    @patch('src.config_manager.get_config_manager')
    def test_get_config_with_credentials(self, mock_get_config_manager):
        """Test getting OAuth config when credentials are set."""
        mock_config_manager = Mock()
        mock_config_manager.get_config.return_value = {
            "plugins": {
                "spotify": {
                    "client_id": "test_client_id",
                    "client_secret": "test_client_secret"
                }
            }
        }
        mock_get_config_manager.return_value = mock_config_manager
        
        provider = SpotifyOAuthProvider()
        config = provider.get_config("default")
        
        assert config is not None
        assert config.client_id == "test_client_id"
        assert config.client_secret == "test_client_secret"
        assert config.scope == "user-read-currently-playing"
    
    @patch('src.config_manager.get_config_manager')
    def test_get_config_missing_credentials(self, mock_get_config_manager):
        """Test getting OAuth config when credentials are missing."""
        mock_config_manager = Mock()
        mock_config_manager.get_config.return_value = {"plugins": {}}
        mock_get_config_manager.return_value = mock_config_manager
        
        provider = SpotifyOAuthProvider()
        config = provider.get_config("default")
        
        assert config is None
    
    @patch('src.config_manager.get_config_manager')
    def test_get_authorization_url(self, mock_get_config_manager):
        """Test generating authorization URL."""
        mock_config_manager = Mock()
        mock_config_manager.get_config.return_value = {
            "plugins": {
                "spotify": {
                    "client_id": "test_client",
                    "client_secret": "test_secret"
                }
            }
        }
        mock_get_config_manager.return_value = mock_config_manager
        
        provider = SpotifyOAuthProvider()
        url = provider.get_authorization_url("default", "state_123")
        
        assert "accounts.spotify.com/authorize" in url
        assert "client_id=test_client" in url
        assert "state=state_123" in url
        assert "scope=user-read-currently-playing" in url
    
    @patch('src.config_manager.get_config_manager')
    @patch('requests.post')
    def test_exchange_code_for_tokens(self, mock_post, mock_get_config_manager):
        """Test exchanging authorization code for tokens."""
        mock_config_manager = Mock()
        mock_config_manager.get_config.return_value = {
            "plugins": {
                "spotify": {
                    "client_id": "test_client",
                    "client_secret": "test_secret"
                }
            }
        }
        mock_get_config_manager.return_value = mock_config_manager
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "access_123",
            "refresh_token": "refresh_456",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "user-read-currently-playing"
        }
        mock_post.return_value = mock_response
        
        provider = SpotifyOAuthProvider()
        tokens = provider.exchange_code_for_tokens("default", "auth_code_789")
        
        assert tokens.access_token == "access_123"
        assert tokens.refresh_token == "refresh_456"
        assert tokens.expires_in == 3600
    
    @patch('src.config_manager.get_config_manager')
    @patch('requests.post')
    def test_exchange_code_failure(self, mock_post, mock_get_config_manager):
        """Test token exchange failure handling."""
        mock_config_manager = Mock()
        mock_config_manager.get_config.return_value = {
            "plugins": {
                "spotify": {
                    "client_id": "test_client",
                    "client_secret": "test_secret"
                }
            }
        }
        mock_get_config_manager.return_value = mock_config_manager
        
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Invalid code"
        mock_post.return_value = mock_response
        
        provider = SpotifyOAuthProvider()
        
        with pytest.raises(ValueError, match="Token exchange failed"):
            provider.exchange_code_for_tokens("default", "bad_code")
    
    @patch('src.config_manager.get_config_manager')
    @patch('src.security.secrets_manager.get_secrets_manager')
    @patch('requests.post')
    def test_refresh_access_token(self, mock_post, mock_get_secrets, mock_get_config_manager):
        """Test refreshing access token."""
        mock_config_manager = Mock()
        mock_config_manager.get_config.return_value = {
            "plugins": {
                "spotify": {
                    "client_id": "test_client",
                    "client_secret": "test_secret"
                }
            }
        }
        mock_get_config_manager.return_value = mock_config_manager
        
        mock_secrets = Mock()
        mock_secrets.get_secret.return_value = "refresh_token_123"
        mock_get_secrets.return_value = mock_secrets
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_access_456",
            "expires_in": 3600
        }
        mock_post.return_value = mock_response
        
        provider = SpotifyOAuthProvider()
        tokens = provider.refresh_access_token("default")
        
        assert tokens is not None
        assert tokens.access_token == "new_access_456"
        assert tokens.expires_in == 3600
    
    @patch('src.security.secrets_manager.get_secrets_manager')
    def test_store_tokens(self, mock_get_secrets):
        """Test storing OAuth tokens."""
        mock_secrets = Mock()
        mock_get_secrets.return_value = mock_secrets
        
        provider = SpotifyOAuthProvider()
        tokens = OAuthTokens(
            access_token="access_123",
            refresh_token="refresh_456",
            expires_in=3600,
            scope="test_scope"
        )
        
        provider.store_tokens("default", tokens)
        
        # Verify secrets were stored
        assert mock_secrets.set_secret.call_count == 4  # access, refresh, expires_at, scope
    
    @patch('src.security.secrets_manager.get_secrets_manager')
    def test_get_access_token_valid(self, mock_get_secrets):
        """Test getting a valid access token."""
        mock_secrets = Mock()
        mock_secrets.get_secret.side_effect = lambda ns, key: {
            "access_token": "valid_token",
            "expires_at": str(time.time() + 3600)  # Expires in 1 hour
        }.get(key)
        mock_get_secrets.return_value = mock_secrets
        
        provider = SpotifyOAuthProvider()
        token = provider.get_access_token("default")
        
        assert token == "valid_token"
    
    @patch('src.security.secrets_manager.get_secrets_manager')
    def test_get_access_token_not_found(self, mock_get_secrets):
        """Test getting access token when none stored."""
        mock_secrets = Mock()
        mock_secrets.get_secret.return_value = None
        mock_get_secrets.return_value = mock_secrets
        
        provider = SpotifyOAuthProvider()
        token = provider.get_access_token("default")
        
        assert token is None
    
    @patch('src.security.secrets_manager.get_secrets_manager')
    def test_clear_tokens(self, mock_get_secrets):
        """Test clearing stored tokens."""
        mock_secrets = Mock()
        mock_get_secrets.return_value = mock_secrets
        
        provider = SpotifyOAuthProvider()
        provider.clear_tokens("default")
        
        mock_secrets.delete_secret.assert_called_once_with("spotify:default")


class TestOAuthProviderRegistry:
    """Tests for OAuth provider registry."""
    
    def test_get_spotify_provider(self):
        """Test getting Spotify provider from registry."""
        provider = get_oauth_provider("spotify")
        
        assert provider is not None
        assert provider.provider_id == "spotify"
        assert isinstance(provider, SpotifyOAuthProvider)
    
    def test_get_nonexistent_provider(self):
        """Test getting a provider that doesn't exist."""
        provider = get_oauth_provider("nonexistent_provider")
        
        assert provider is None
    
    def test_list_oauth_providers(self):
        """Test listing all OAuth providers."""
        providers = list_oauth_providers()
        
        assert "spotify" in providers
    
    def test_register_custom_provider(self):
        """Test registering a custom OAuth provider."""
        class CustomProvider(OAuthProvider):
            @property
            def provider_id(self):
                return "test_custom"
            
            @property
            def provider_name(self):
                return "Test Custom"
            
            def get_config(self, board_id):
                return None
            
            def get_authorization_url(self, board_id, state):
                return "https://test.com/authorize"
            
            def exchange_code_for_tokens(self, board_id, code):
                return OAuthTokens(access_token="test")
            
            def refresh_access_token(self, board_id):
                return None
        
        custom = CustomProvider()
        register_oauth_provider(custom)
        
        retrieved = get_oauth_provider("test_custom")
        assert retrieved is custom
        assert retrieved.provider_id == "test_custom"
