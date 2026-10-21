# Portable local deployment

## Contract

`hymio init` creates one private input file, `~/.hymio/config.toml` (or `--config PATH`).
MiniMax and E2B API keys are the only required external credentials. Environment variables
`MINIMAX_API_KEY` and `E2B_API_KEY` override the file; an environment-only deployment can leave
its key values empty. Model IDs, endpoint, E2B template, Casdoor port and LAN host are optional.
Unknown fields, missing credentials and invalid endpoints fail before starting services.

`hymio start` detects this file and generates separate Backend/Oath configurations and internal
credentials under a private local runtime directory. These generated files are outputs, never
additional operator inputs. Oath remains independent; Hymio uses its configuration/CLI contract
and imports the model key to Vault through the Oath process environment only. A digest-derived
credential alias changes when the key changes; restart seeds the new alias without overwriting
a previous credential used by existing work. Old aliases remain in Vault.

## Initialization and recovery

A per-configuration runtime directory is protected by the launcher lock. Internal credentials are
created once, written atomically and reused after interruption. Casdoor uses a dedicated Compose
project/volume; it never adopts an unrelated database or kills a service occupying its port.
A seed file creates the Hymio organization, minimal password signup application and a private
JWT signing certificate. Casdoor `initDataNewOnly` preserves existing users/application/admin
changes on later starts. The initial administrator password is random and stored privately.
The issuer and discovery health check use the configured Casdoor port; Backend/client retain
8080/1420 for compatibility with the existing lifecycle manager.

The E2B template is checked on startup; an absent template is built once using the existing
Hymio Desktop recipe. Provider errors fail with a credential-safe diagnostic and do not trigger
repeated builds. No sandbox is created just to test configuration.

## Portability and compatibility

Copying only the input file to another machine creates a fresh independent deployment: new
internal credentials, identities and storage. API accounts/template aliases and their billing are
shared when keys are reused. Account/history migration requires a separate consistent data backup;
copying generated credentials or Vault AppRole files is not a migration procedure.

Existing deployments without this input keep their legacy TOML paths and Casdoor project.
Explicit `--backend-config`/`--oath-config` select the legacy workflow; mixing these with `--config`
is rejected. Initialization does not overwrite an existing input file. Custom input files have
separate runtime directories. Secrets do not enter command arguments, logs, examples or Git. The external key environment
is removed before starting Backend/client children. Mounted Oath configuration, verifier token
and AppRole files are readable inside non-root containers under 0700 host runtime ancestors;
the operator input and Vault administrator material stay 0600. Product tools are staged per
runtime so their private Backend connection never modifies another deployment's extension mount.

The feature is the macOS/Linux local source deployment. Existing cloud deployment inputs and
Google/OIDC customization remain supported through their own documented workflows; no cloud
migration or unattended dependency installation is implied.
