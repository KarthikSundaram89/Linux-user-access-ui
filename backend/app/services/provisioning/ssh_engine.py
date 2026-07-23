"""
SSH Engine - Handles SSH connections and remote command execution.
Supports RSA, ECDSA, and ED25519 keys.
"""

import io
import logging
import asyncio
from typing import Optional, Tuple
from dataclasses import dataclass

import paramiko

from ...core.config import settings
from ...core.security import decrypt_value

logger = logging.getLogger(__name__)


@dataclass
class SSHResult:
    """Result of an SSH command execution."""
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    hostname: str
    error_message: Optional[str] = None


class SSHEngine:
    """
    SSH Engine for remote server provisioning.
    Supports concurrent connections, retries, and comprehensive logging.
    """

    def __init__(self):
        self.timeout = settings.SSH_TIMEOUT
        self.max_retries = settings.SSH_RETRIES
        self.retry_delay = settings.SSH_RETRY_DELAY
        self.concurrent_limit = settings.SSH_CONCURRENT_LIMIT
        self._semaphore = asyncio.Semaphore(self.concurrent_limit)

    async def execute_on_server(
        self,
        hostname: str,
        script: str,
        private_key_encrypted: str,
        passphrase_encrypted: Optional[str] = None,
        username: str = "root",
        port: int = 22,
    ) -> SSHResult:
        """
        Execute a script on a remote server via SSH.
        Handles connection, authentication, execution, and retry logic.
        """
        async with self._semaphore:
            last_error = None

            for attempt in range(1, self.max_retries + 1):
                try:
                    logger.info(f"SSH attempt {attempt}/{self.max_retries} to {hostname}")
                    result = await asyncio.to_thread(
                        self._execute_sync,
                        hostname=hostname,
                        script=script,
                        private_key_encrypted=private_key_encrypted,
                        passphrase_encrypted=passphrase_encrypted,
                        username=username,
                        port=port,
                    )
                    return result

                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"SSH attempt {attempt} failed for {hostname}: {last_error}")

                    if attempt < self.max_retries:
                        await asyncio.sleep(self.retry_delay)

            return SSHResult(
                success=False,
                stdout="",
                stderr="",
                exit_code=-1,
                hostname=hostname,
                error_message=f"All {self.max_retries} attempts failed. Last error: {last_error}",
            )

    def _execute_sync(
        self,
        hostname: str,
        script: str,
        private_key_encrypted: str,
        passphrase_encrypted: Optional[str],
        username: str,
        port: int,
    ) -> SSHResult:
        """Synchronous SSH execution (run in thread pool)."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            # Decrypt private key
            private_key_pem = decrypt_value(private_key_encrypted)
            passphrase = decrypt_value(passphrase_encrypted) if passphrase_encrypted else None

            # Load the key
            key = self._load_private_key(private_key_pem, passphrase)

            # Connect
            client.connect(
                hostname=hostname,
                port=port,
                username=username,
                pkey=key,
                timeout=self.timeout,
                allow_agent=False,
                look_for_keys=False,
            )

            # Execute script
            stdin, stdout, stderr = client.exec_command(
                script,
                timeout=self.timeout * 2,
            )

            exit_code = stdout.channel.recv_exit_status()
            stdout_text = stdout.read().decode("utf-8", errors="replace")
            stderr_text = stderr.read().decode("utf-8", errors="replace")

            return SSHResult(
                success=(exit_code == 0),
                stdout=stdout_text,
                stderr=stderr_text,
                exit_code=exit_code,
                hostname=hostname,
            )

        except paramiko.AuthenticationException as e:
            return SSHResult(
                success=False, stdout="", stderr="", exit_code=-1,
                hostname=hostname, error_message=f"Authentication failed: {str(e)}"
            )
        except paramiko.SSHException as e:
            return SSHResult(
                success=False, stdout="", stderr="", exit_code=-1,
                hostname=hostname, error_message=f"SSH error: {str(e)}"
            )
        except TimeoutError:
            return SSHResult(
                success=False, stdout="", stderr="", exit_code=-1,
                hostname=hostname, error_message=f"Connection timed out after {self.timeout}s"
            )
        except Exception as e:
            return SSHResult(
                success=False, stdout="", stderr="", exit_code=-1,
                hostname=hostname, error_message=f"Unexpected error: {str(e)}"
            )
        finally:
            client.close()

    def _load_private_key(self, key_pem: str, passphrase: Optional[str]) -> paramiko.PKey:
        """Load a private key from PEM string. Supports RSA, ECDSA, ED25519."""
        key_file = io.StringIO(key_pem)
        password = passphrase.encode() if passphrase else None

        # Try RSA first
        try:
            return paramiko.RSAKey.from_private_key(key_file, password=password)
        except (paramiko.SSHException, ValueError):
            key_file.seek(0)

        # Try ECDSA
        try:
            return paramiko.ECDSAKey.from_private_key(key_file, password=password)
        except (paramiko.SSHException, ValueError):
            key_file.seek(0)

        # Try ED25519
        try:
            return paramiko.Ed25519Key.from_private_key(key_file, password=password)
        except (paramiko.SSHException, ValueError):
            pass

        raise ValueError("Could not load private key. Supported types: RSA, ECDSA, ED25519")

    async def test_connection(
        self,
        hostname: str,
        private_key_encrypted: str,
        passphrase_encrypted: Optional[str] = None,
        username: str = "root",
        port: int = 22,
    ) -> SSHResult:
        """Test SSH connection to a server."""
        return await self.execute_on_server(
            hostname=hostname,
            script="echo 'Connection successful' && hostname && whoami",
            private_key_encrypted=private_key_encrypted,
            passphrase_encrypted=passphrase_encrypted,
            username=username,
            port=port,
        )

    async def execute_on_multiple_servers(
        self,
        hostnames: list[str],
        script: str,
        private_key_encrypted: str,
        passphrase_encrypted: Optional[str] = None,
        username: str = "root",
        port: int = 22,
    ) -> list[SSHResult]:
        """Execute a script on multiple servers concurrently."""
        tasks = [
            self.execute_on_server(
                hostname=hostname,
                script=script,
                private_key_encrypted=private_key_encrypted,
                passphrase_encrypted=passphrase_encrypted,
                username=username,
                port=port,
            )
            for hostname in hostnames
        ]
        return await asyncio.gather(*tasks)
