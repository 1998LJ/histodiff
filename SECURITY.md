# Security Policy

## Supported versions

histodiff is pre-1.0 (the `0.x` series) and publishes a single line of
releases - there is no long-term-support branch. Security fixes are made
against `main` and released as the next `0.x` version.

| Version | Supported |
| --- | --- |
| Latest release on PyPI | :white_check_mark: |
| Anything older | :x: |

If you're on an older release, please upgrade before reporting an issue; a
fix will only be backported in unusual circumstances (for example, an
actively exploited vulnerability with no other mitigation).

## Reporting a vulnerability

Please **do not** open a public GitHub issue for a suspected security
vulnerability. A public issue discloses it to everyone, including anyone
who might exploit it, before a fix exists.

Instead, please use GitHub's private vulnerability reporting for this
repository:

1. Go to the repository's
   [Security tab](https://github.com/rmnvg/histodiff/security).
2. Click **"Report a vulnerability"**.
3. Describe the issue, the affected version(s), and, if you can, a minimal
   reproduction.

This opens a private advisory visible only to you and the maintainers, with
its own discussion thread, until a fix is ready and you agree to disclose it.

<!--
  Maintainers: private vulnerability reporting must be turned on for this
  feature to be available to reporters - enable it under this repository's
  Settings -> Security -> "Private vulnerability reporting". Consider also
  adding a maintainer contact email above as a fallback for reporters who
  don't have (or don't want) a GitHub account.
-->

### What counts as a security issue here

histodiff is a text-diffing library and CLI: it reads two files, or two
sequences in Python, and produces a description of their differences. Worth
reporting privately, for example:

- A crash, hang, or excessive memory/CPU use triggered by untrusted input,
  beyond what's already documented in the README's
  [Limitations](https://github.com/rmnvg/histodiff/blob/main/README.md#limitations)
  and [Performance](https://github.com/rmnvg/histodiff/blob/main/README.md#performance)
  sections - for example, a way to hit worst-case behavior far more cheaply
  than the documented cost, or exhaust memory on a small input.
- Any way that diffing two inputs could execute code, or read or write
  files other than the ones explicitly passed in.
- A vulnerability in a dependency that affects histodiff specifically. Note
  that histodiff itself has no runtime dependencies; this would most likely
  concern the `dev` extra or the build/release toolchain instead.

Bugs that only affect diff *quality* - an unexpected alignment, a
diff that's larger or less readable than expected - are not security
issues. Please file those as a normal
[bug report](https://github.com/rmnvg/histodiff/issues/new/choose) instead.

## Response policy

These are best-effort targets from an unpaid open-source project, not a
contractual SLA:

- Acknowledge a new report within **5 business days**.
- Provide an initial assessment - confirmed, not a security issue, or more
  information needed - within **10 business days** of acknowledgment.
- Once a fix is ready, coordinate a release and, unless you ask otherwise,
  credit you in the release notes and/or a GitHub Security Advisory.
