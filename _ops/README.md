# `_ops/` — field scripts

Scripts written while building and debugging against a real TNAS. They are not
part of the package and never run on a user's device; they exist so that the
next person does not have to rediscover what each one found.

**Nothing here is exercised by the submission gate.** The gate is `tools/`;
these are the tools that produced the findings recorded in `docs/开发文档.md`.

## Credentials

No device credential is stored in this directory. Every script takes its
connection details from the environment and stops with an explanation if they
are missing:

```bash
export PRINT_HOST=10.0.0.10      # the NAS
export PRINT_PORT=22             # its SSH port
export PRINT_USER=admin
export PRINT_PASS=...
```

The two browser harnesses use a second set, because they talk to the TOS web
interface rather than SSH:

```bash
export PRINT_WEB=http://10.0.0.10:8181
export PRINT_WEB_USER=admin
export PRINT_WEB_PASS=...
```

`_device.py` holds the lookup. A credential with a default value is a credential
in the repository, and this repository is the input to the packaging pipeline.

## What each script is for

| Script | What it does |
|---|---|
| `_deploy.py` | Install the built `.deb` on a device and verify the whole installation: digest, service state, every served frontend file against the repository, the application's own environment check, and the notes library probed **as the application user** rather than as root |
| `_live_verify_marknest.py` | Drive the real TOS desktop in a browser: open the application as an embedded window, confirm the platform identity reaches it through the proxy, then create, edit, preview, save and delete a note |
| `_install_web_route.py` | Give the application a web route. The platform creates its own nginx `AppAccessControl` config when it installs from the App Center, and a hand-installed `.deb` gets none — this writes one, derived from an application the platform already installed |
| `_fix_share_owner.py` | Recreate the notes share with the right owner. `ter_share_add` bakes the owner into the SPC ACL, so a share created for a different account cannot be entered by this one, and `postinst`'s chown of the subtree cannot help |
| `_probe_web_route.py` | Why does `/marknest/` answer 301/403 when the service is fine? |
| `_probe_identity_socket.py` | Is the user cookie reaching the application at all? Separates "the application cannot read it" from "the proxy never forwards it" |
| `_probe_identity_cookie.py` | What cookies does a signed-in session actually carry? |
| `_probe_after_deploy.py` | The three things the first deployment got wrong, in one run |
| `_push_to_nas.py` | Copy the built `.deb` to the team share, with the digest compared on the far side |

## Notes on running them

- Most are **read-only**; the ones that change the device say so in their own
  docstring and take `--commit` before doing anything.
- `_deploy.py` and `_install_web_route.py` **change the device**. Read them
  first.
- `_push_to_nas.py` and `_fix_share_owner.py` need a path that exists on that
  particular NAS (`/Volume1/public/claude`, `/Volume1/marknest-data`); adjust if
  yours differs.
