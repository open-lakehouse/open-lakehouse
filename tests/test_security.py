"""
Security tests for lakehouse-stack.

These tests verify that security safeguards are in place and working correctly.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

# Get project root
PROJECT_ROOT = Path(__file__).parent.parent


class TestSecretsDetection:
    """Tests to ensure no secrets are committed."""

    @pytest.mark.security
    def test_no_hardcoded_passwords_in_scripts(self):
        """Ensure no hardcoded passwords in Python scripts."""
        scripts_dir = PROJECT_ROOT / "scripts"
        password_patterns = [
            r'password\s*=\s*["\'][^"\']+["\']',
            r'secret\s*=\s*["\'][^"\']+["\']',
            r'api_key\s*=\s*["\'][^"\']+["\']',
            r'token\s*=\s*["\'][^"\']+["\']',
        ]

        violations = []
        for py_file in scripts_dir.glob("*.py"):
            content = py_file.read_text()
            for pattern in password_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                # Filter out obvious placeholders
                for match in matches:
                    if not any(
                        placeholder in match.lower()
                        for placeholder in [
                            "your_",
                            "example",
                            "placeholder",
                            "changeme",
                            "xxx",
                            "***",
                            "${",
                            "env.",
                        ]
                    ):
                        violations.append(f"{py_file.name}: {match}")

        assert not violations, f"Potential hardcoded secrets found:\n" + "\n".join(
            violations
        )

    @pytest.mark.security
    def test_env_file_not_committed(self):
        """Ensure .env file is not tracked by git."""
        result = subprocess.run(
            ["git", "ls-files", ".env"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        assert not result.stdout.strip(), ".env file should not be tracked by git"

    @pytest.mark.security
    def test_spark_defaults_not_committed(self):
        """Ensure spark-defaults.conf is not tracked by git."""
        result = subprocess.run(
            ["git", "ls-files", "config/spark/spark-defaults.conf"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        assert (
            not result.stdout.strip()
        ), "spark-defaults.conf should not be tracked by git"

    @pytest.mark.security
    def test_gitignore_has_sensitive_patterns(self):
        """Ensure .gitignore includes patterns for sensitive files."""
        gitignore_path = PROJECT_ROOT / ".gitignore"
        assert gitignore_path.exists(), ".gitignore file must exist"

        content = gitignore_path.read_text()
        required_patterns = [
            ".env",
            "spark-defaults.conf",
            "*.pem",
            "*.key",
        ]

        missing = [p for p in required_patterns if p not in content]
        assert not missing, f"Missing patterns in .gitignore: {missing}"


class TestInputValidation:
    """Tests for input validation in shell scripts."""

    @pytest.mark.security
    def test_lakehouse_script_validates_filenames(self):
        """Ensure migration filenames are validated."""
        lakehouse_path = PROJECT_ROOT / "lakehouse"
        content = lakehouse_path.read_text()

        # Check for filename validation regex
        assert (
            "^[a-zA-Z0-9_.-]+\\.sql$" in content
        ), "Migration filename validation should be present"

    @pytest.mark.security
    def test_lakehouse_script_escapes_sql(self):
        """Ensure SQL values are escaped."""
        lakehouse_path = PROJECT_ROOT / "lakehouse"
        content = lakehouse_path.read_text()

        # Check for SQL escaping (single quote doubling)
        assert (
            "//\\'/\\'\\'" in content or "safe_filename" in content
        ), "SQL escaping should be present"

    @pytest.mark.security
    def test_no_unsafe_eval_with_user_input(self):
        """Ensure eval is not used with potentially unsafe input."""
        lakehouse_path = PROJECT_ROOT / "lakehouse"
        content = lakehouse_path.read_text()

        # Check that wait_for_service validates commands
        assert (
            'check_cmd" =~ ^(nc\\ -z|curl\\ -s|docker\\ exec|PGPASSWORD=)' in content
            or "Invalid check command" in content
        ), "Command validation should be present for wait_for_service"


class TestDockerSecurity:
    """Tests for Docker configuration security."""

    @pytest.mark.security
    def test_compose_files_exist(self):
        """Ensure docker-compose files exist for validation."""
        compose_files = [
            "docker-compose.yml",
            "docker-compose-spark41.yml",
            "docker-compose-kafka.yml",
        ]

        for compose_file in compose_files:
            path = PROJECT_ROOT / compose_file
            assert path.exists(), f"{compose_file} must exist"

    @pytest.mark.security
    def test_no_privileged_containers_in_main_compose(self):
        """Ensure main compose files don't use privileged mode."""
        compose_files = [
            "docker-compose.yml",
            "docker-compose-spark41.yml",
            "docker-compose-kafka.yml",
        ]

        for compose_file in compose_files:
            path = PROJECT_ROOT / compose_file
            if path.exists():
                content = path.read_text()
                assert (
                    "privileged: true" not in content
                ), f"{compose_file} should not use privileged mode"


class TestCISecurityConfig:
    """Tests for CI/CD security configuration."""

    @pytest.mark.security
    def test_github_actions_pinned(self):
        """Ensure GitHub Actions are pinned to commit SHAs."""
        ci_path = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
        if not ci_path.exists():
            pytest.skip("CI workflow not found")

        content = ci_path.read_text()

        # Check for SHA-pinned actions (40 hex chars)
        uses_lines = [
            line for line in content.split("\n") if "uses: actions/" in line
        ]

        for line in uses_lines:
            # Should have a 40-char SHA, not just a version tag
            assert re.search(
                r"@[a-f0-9]{40}", line
            ), f"Action should be pinned to SHA: {line.strip()}"

    @pytest.mark.security
    def test_ci_has_permissions_block(self):
        """Ensure CI workflow has restricted permissions."""
        ci_path = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
        if not ci_path.exists():
            pytest.skip("CI workflow not found")

        content = ci_path.read_text()
        assert "permissions:" in content, "CI should have permissions block"
        assert (
            "contents: read" in content
        ), "CI should have minimal permissions (contents: read)"

    @pytest.mark.security
    def test_no_curl_pipe_to_shell(self):
        """Ensure no curl | sh patterns in CI."""
        ci_path = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
        if not ci_path.exists():
            pytest.skip("CI workflow not found")

        content = ci_path.read_text()

        # Match patterns like: curl URL | sh, curl URL | bash, etc.
        # The \| escapes the literal pipe character
        dangerous_patterns = [
            r"curl\s+[^\|]+\|\s*sh\b",
            r"curl\s+[^\|]+\|\s*bash\b",
            r"curl\s+[^\|]+\|\s*python",
            r"wget\s+[^\|]+\|\s*sh\b",
            r"wget\s+[^\|]+\|\s*bash\b",
        ]

        for pattern in dangerous_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            assert (
                not matches
            ), f"Dangerous curl-pipe-to-shell pattern found: {matches}"


class TestPreCommitConfig:
    """Tests for pre-commit configuration."""

    @pytest.mark.security
    def test_precommit_config_exists(self):
        """Ensure pre-commit config exists."""
        config_path = PROJECT_ROOT / ".pre-commit-config.yaml"
        assert config_path.exists(), "pre-commit config should exist"

    @pytest.mark.security
    def test_precommit_has_secrets_detection(self):
        """Ensure pre-commit includes secrets detection."""
        config_path = PROJECT_ROOT / ".pre-commit-config.yaml"
        if not config_path.exists():
            pytest.skip("pre-commit config not found")

        content = config_path.read_text()
        assert (
            "detect-secrets" in content or "detect-private-key" in content
        ), "pre-commit should include secrets detection"

    @pytest.mark.security
    def test_precommit_has_security_scanner(self):
        """Ensure pre-commit includes security scanner."""
        config_path = PROJECT_ROOT / ".pre-commit-config.yaml"
        if not config_path.exists():
            pytest.skip("pre-commit config not found")

        content = config_path.read_text()
        assert "bandit" in content, "pre-commit should include bandit security scanner"


class TestFilePermissions:
    """Tests for file permission recommendations."""

    @pytest.mark.security
    def test_env_example_not_executable(self):
        """Ensure example files are not executable."""
        env_example = PROJECT_ROOT / ".env.example"
        if env_example.exists():
            mode = env_example.stat().st_mode
            # Check that execute bits are not set (for user, group, or other)
            assert not (mode & 0o111), ".env.example should not be executable"

    @pytest.mark.security
    def test_scripts_are_executable(self):
        """Ensure shell scripts are executable."""
        scripts = [
            PROJECT_ROOT / "lakehouse",
            PROJECT_ROOT / "scripts" / "download-jars.sh",
        ]

        for script in scripts:
            if script.exists():
                mode = script.stat().st_mode
                assert mode & 0o100, f"{script.name} should be executable"
