# Security Policy

Please use [GitHub private vulnerability reporting](https://github.com/jessenkurien/cyber-pnl/security/advisories/new)
for a suspected vulnerability, including a way to bypass schema or digest verification, alter statement
figures without changing the digest, escape intended report output paths, or execute code through a
crafted model file. Do not include a real organization's model or sensitive figures in the report.

The runtime reads YAML and writes reports. It makes no network calls and uses safe YAML loading. A
digest attestation is not identity authentication: anyone who can edit the model can also create a new
YAML attestation. Protect operational models in a private repository, restrict write access, and use an
authenticated approval/signing system where required.
