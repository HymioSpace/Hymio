# Agent and cloud-computer diagnostics

## Host I/O and file-cache thrashing

When all APIs and Docker commands slow together, inspect the host before restarting services:

```sh
vmstat 1 5
iostat -xz 1 5
grep -E 'MemAvailable|Cached|Dirty|Writeback|AnonHugePages' /proc/meminfo
grep -E 'workingset_refault_file|pgscan_kswapd|pgsteal_kswapd' /proc/vmstat
grep . /sys/kernel/mm/transparent_hugepage/hugepages-*/file_enabled
```

Ignore the first `vmstat`/`iostat` report, which includes statistics since boot. Compare
counter deltas across samples. A high load with high `wa` means blocked I/O, not necessarily
CPU exhaustion. Distinguish read BPS from write BPS; free disk space does not measure latency.

For service attribution, sample `io.stat` twice under `/sys/fs/cgroup/system.slice/*/`
and divide byte deltas by elapsed seconds. `/proc/PID/io` helps identify processes, but
short-lived children can disappear between samples and parent counters can include waited
children. Do not sum parent and child process counters as independent device traffic.

On Alibaba Cloud Linux with file-backed THP enabled, fragmented memory can coincide with
heavy file-cache reclaim and repeated executable reads. This can affect monitoring and system
services as well as application containers. Test the opt-in
[file-cache workaround](cloud/README.md#file-cache-read-thrashing-on-alibaba-cloud-linux),
then verify declining refault/reclaim rates, low I/O wait and actual application requests.
Keep initial policy values for rollback. Do not clear page cache or disable health checks
as a substitute for attribution.

The Oath node exporter supplies host disk, CPU, memory and VM counters. File-cache refault
and disk-latency alerts complement low-memory and free-space alerts. Rules are evaluated
in Prometheus; notifications require a separately configured Alertmanager route.

Start with the failing boundary. WebSocket connected and `/health` returning `200` only prove
that the proxy and HTTP process are alive. They do not prove that a worker can build a context,
call the model or execute a device command.

## Local logs

```sh
hymio status
hymio doctor
hymio logs
hymio logs -f
```

The managed log is `~/.hymio/hymio.log`. Search it without dumping credentials:

```sh
rg -n "Agent upstream|Worker failed|Traceback|model|timeout|429|401|403" \
  ~/.hymio/hymio.log | tail -n 120
```

## Current cloud deployment

Run from a trusted administrative terminal. Keep Workbench credentials and the instance ID
private.

```sh
workbench exec -i INSTANCE_ID -r cn-hongkong -c \
  'docker ps --format "{{.Names}} {{.Status}}"'
workbench exec -i INSTANCE_ID -r cn-hongkong -c \
  'docker logs --timestamps --since 30m --tail 300 hymio-cloud-backend-1'
workbench exec -i INSTANCE_ID -r cn-hongkong -c \
  'docker logs --timestamps --since 30m --tail 300 oath-worker-1'
workbench exec -i INSTANCE_ID -r cn-hongkong -c \
  'journalctl -u hymio-cloud -n 100 --no-pager'
```

The public entry should report:

```sh
curl --fail https://agent.hymio.top/health
curl --fail https://agent.hymio.top/auth/options
```

Then send one short message from a real client. Health checks do not replace an end-to-end model
turn.

## Symptom matrix

| Observation | First check | Meaning |
| --- | --- | --- |
| WS accepted, no reply | `oath-worker-1` logs | Worker may be failing before the model call |
| `PermissionError` on `SKILL.md` | Bind-mount modes and owning UID | Container UID cannot read an operator file |
| `Worker failed; durable step remains recoverable` | Lines immediately above it | The step did not execute; this is not proof of an LLM failure |
| Upstream closes immediately | `oath-gateway-1` logs and configured `oath_ws` | Proxy target, protocol or credentials are wrong |
| Worker reaches provider but gets authentication/quota errors | Worker/provider log lines | This is where model credentials, access or balance matter |
| Model returns but tool call hangs | `oath-tools-1` and Backend device logs | Device transport, deadline or execution lock |
| Device reports preparing for too long | Backend device/recovery records | Provisioning is uncertain; do not create another sandbox blindly |

The observed “WS and HTTP OK but Agent silent” incident was a file-permission failure: the Oath
worker could not read `extensions/skills/*/SKILL.md`, so every durable step failed during context
assembly. Make skill directories traversable and files readable by the Oath application UID
(`10001`), then restart the worker:

```sh
python3 /opt/hymio/repos/Hymio/deploy/cloud/runtime_permissions.py \
  --extensions /opt/hymio/repos/Hymio/extensions --fix
docker restart oath-worker-1
```

Keep private files such as `extensions/tools/_connection.local` mode `600` and owned by UID
`10001`; do not apply `644` recursively to the whole extensions tree.

## Model API failures

When the worker reaches the model, look for provider authentication, model-not-found, rate-limit,
timeout or balance errors. Backend's `model_unavailable` response means the configured model
access or balance must be checked; do not retry a rejected paid request in a loop.

Useful boundaries:

```text
Client WS
  -> Hymio Backend proxy
  -> Oath gateway
  -> Oath worker context assembly
  -> configured LLM provider and Vault credential
  -> Oath tools
  -> Hymio device API
  -> Daytona / E2B / operator ECS
```

Never paste `.toml` files containing keys, browser storage, Vault AppRole values or complete
process environments into an issue. Log identifiers and error classes are usually enough.
