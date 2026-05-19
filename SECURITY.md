# Security Policy for open-lakehouse

## Reporting Security Vulnerabilities

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT** open a public GitHub issue
2. Email the maintainer directly or use GitHub's private security advisory feature
3. Include detailed steps to reproduce the vulnerability
4. Allow reasonable time for a fix before public disclosure

## Security Guidelines for Contributors

### Secrets Management

**NEVER commit:**
- `.env` files with real credentials
- `config/spark/spark-defaults.conf` with real credentials
- Private keys, certificates, or tokens
- Database connection strings with embedded passwords

**Always use:**
- `.env.example` and `*.example` files for templates
- Environment variables for sensitive configuration
- GitHub Secrets for CI/CD credentials

### Pre-commit Hooks

Install pre-commit hooks to catch security issues before committing:

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

The hooks include:
- **detect-secrets**: Scans for hardcoded secrets
- **detect-private-key**: Catches accidentally committed keys
- **bandit**: Python security linter
- **shellcheck**: Shell script security linting

### Input Validation

When writing shell scripts:

```bash
# BAD: Direct variable interpolation in SQL
psql -c "SELECT * FROM users WHERE name = '$user_input'"

# GOOD: Validate and escape input
if [[ ! "$filename" =~ ^[a-zA-Z0-9_.-]+$ ]]; then
    echo "Invalid input"
    exit 1
fi
safe_value="${value//\'/\'\'}"  # Escape single quotes
```

When writing Python:
- Use parameterized queries for SQL
- Validate file paths to prevent traversal
- Sanitize user input before shell commands

### Docker Security

**Avoid:**
- `network_mode: host` in production
- Running containers as root
- Disabling authentication (e.g., Jupyter tokens)
- Using `privileged: true`

**Prefer:**
- Bridge networking with explicit port mappings
- Non-root container users
- Proper authentication for all services
- Minimal container capabilities

### CI/CD Security

**GitHub Actions:**
- Pin actions to full commit SHAs, not tags
- Use minimal permissions (`contents: read`)
- Never pipe curl/wget output directly to shell
- Use GitHub Secrets for all credentials

```yaml
# BAD
- uses: actions/checkout@v4

# GOOD
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
```

### Code Review Checklist

Before approving PRs, verify:

- [ ] No hardcoded credentials or secrets
- [ ] Input validation for user-controlled data
- [ ] SQL queries use parameterization
- [ ] Shell commands don't use unsafe `eval`
- [ ] Docker configs don't expose unnecessary privileges
- [ ] CI changes don't introduce security regressions
- [ ] New dependencies don't have known vulnerabilities

## Security Tests

Run security-focused tests:

```bash
# Run security tests only
poetry run pytest tests/test_security.py -v

# Run with security marker
poetry run pytest -m security -v
```

## Dependency Security

Check for vulnerable dependencies:

```bash
# Using pip-audit
pip install pip-audit
pip-audit

# Using safety
pip install safety
safety check
```

## Network Security Recommendations

For production deployments:

1. **Use TLS everywhere**
   - Enable SSL for PostgreSQL connections
   - Enable HTTPS for S3/SeaweedFS
   - Use TLS for Kafka (if exposed externally)

2. **Network segmentation**
   - Place services in private subnets
   - Use security groups/firewalls
   - Expose only necessary ports

3. **Authentication**
   - Enable authentication on all services
   - Use strong, unique passwords
   - Rotate credentials regularly

## Incident Response

If you suspect a security breach:

1. Rotate all credentials immediately
2. Review access logs
3. Check for unauthorized changes
4. Document the incident
5. Notify affected parties

## Security Audit Schedule

- **Weekly**: Run `pre-commit run --all-files`
- **Monthly**: Review dependency vulnerabilities
- **Quarterly**: Full security audit of configurations
- **Annually**: Penetration testing (if applicable)
