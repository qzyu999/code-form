# Running and operating code-form

## Requirements and first setup

Use Python 3.11 or newer and Git. Git metadata is optional for analysis, but
Git is needed to clone this repository and run the complete test suite.
The application uses the Python standard library: no API key, database,
Node build, or runtime package installation is required.

Windows / PowerShell:

```powershell
git clone https://github.com/qzyu999/code-form.git
Set-Location code-form
python -m venv --without-pip .venv
.\.venv\Scripts\python.exe --version
```

macOS / Linux:

```bash
git clone https://github.com/qzyu999/code-form.git
cd code-form
python3 -m venv --without-pip .venv
.venv/bin/python --version
```

Use the environment's Python for every subsequent application and test command.
Activation is optional; these instructions use explicit paths.

On Windows, `.\scripts\setup.ps1` performs the environment setup. Pass
`-WithPip` only if you want to provision pip for your own development tools;
pip is unnecessary to operate the app.

## Start and check health

Run the server in a terminal from the checkout:

```powershell
.\.venv\Scripts\python.exe -m codeform serve --demo --data-dir .codeform/demo
```

On macOS/Linux:

```bash
.venv/bin/python -m codeform serve --demo --data-dir .codeform/demo
```

Open **http://127.0.0.1:7331**. Keep that terminal open while using the app.
The command prints the URL and allowed workspace once the server is ready.
With `--demo`, the three examples are analyzed before the URL is printed.
They may appear alongside existing snapshots in that data directory.

The equivalent Windows helper is:

```powershell
.\scripts\start.ps1 -DataDir .codeform/demo
```

Check the running service from a second terminal:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:7331/api/health
```

```bash
curl --fail http://127.0.0.1:7331/api/health
```

The response is `{"status":"ok","version":"0.1.0"}`. This checks HTTP
availability; inspect analysis jobs and findings in the UI to assess a
particular repository.

## Stop and restart

Press **Ctrl+C in the terminal running the server**, then wait for the shell
prompt. Closing a browser tab does not stop the application.

Shutdown closes the HTTP listener, cancels queued analyses that have not
started, and waits for running analyses to finish. Large repositories can
take longer to stop. Snapshots and annotations already saved remain on disk.
Job IDs and queue progress are temporary and do not survive a restart.

Restart by running the same command with the same `--data-dir`. Reload an
already open browser tab after restarting, because the local mutation token
changes each time the service starts. Restart after changing Python code;
there is no development auto-reloader.

If the original terminal is inaccessible, inspect the process listening on
the port before terminating it. On Windows:

```powershell
$listener = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 7331 -State Listen
$servicePid = $listener.OwningProcess | Select-Object -Unique
Get-CimInstance Win32_Process -Filter "ProcessId = $servicePid" |
    Select-Object ProcessId, ExecutablePath, CommandLine
```

Only after confirming it is this checkout's `.venv` Python running
`-m codeform serve`, use `Stop-Process -Id $servicePid`. This is forced
termination, so a running analysis may not finish; re-analyze it after
restart. Avoid stopping all Python processes.

On macOS/Linux, `lsof -nP -iTCP:7331 -sTCP:LISTEN` identifies the listener.
Inspect its command with `ps -p <PID> -o args=`. For this server, `kill -INT
<PID>` requests the same interruption as Ctrl+C.

## Configure scope, storage, and port

| Option | Default | Meaning |
| --- | --- | --- |
| `--workspace DIRECTORY` | Current working directory | Existing directory allowed for UI-selected repositories. Relative input paths begin here. |
| `--data-dir DIRECTORY` | `<workspace>/.codeform` | Snapshot and review storage. An explicit relative value begins at the server's working directory. |
| `--port NUMBER` | `7331` | Loopback HTTP port. Use `0` to choose a free port and read the printed URL. |
| `--demo` | Off | Analyze bundled examples on startup when they are inside the allowed workspace. |

For repositories alongside code-form, allow their common parent but keep
storage in this checkout:

```powershell
.\.venv\Scripts\python.exe -m codeform serve --workspace .. --data-dir .codeform/projects --port 7332
```

The UI opens at http://127.0.0.1:7332. A sibling repo can now be selected
by its name relative to `..`. To use the helper:

```powershell
.\scripts\start.ps1 -Workspace .. -DataDir .codeform/projects -Port 7332 -NoDemo
```

The helper resolves relative workspace and data paths from the checkout
because it changes to that directory before starting Python. Direct CLI
commands resolve their arguments from the terminal's current directory.

Use one server process per data directory. Writes are atomic, and concurrency
is coordinated within a process; there is no cross-process storage lock.

## Analyze and review

1. Select **Analyze repository** and enter an existing Python repository path.
   The resolved path must be inside the server's allowed workspace.
2. Wait for the snapshot to appear. Analysis reads and parses source without
   running the target's code, tests, dependency installers, or scripts.
3. Inspect Architecture and Claim ledger. Open the source behind a claim.
4. Review Findings. Candidate issues include uncertainty and suggested validation.
5. Save a review status and reasoning. Accepting a finding enables a task export
   containing scope, evidence, a proposed test, and acceptance criteria.
6. Validate behavior independently in the target's own controlled test environment.
   The application does not execute exported tasks.
7. Edit the target repository outside code-form, then select **Re-analyze**.
8. Compare its earlier and later snapshots. Review decisions remain attached
   to the snapshot on which they were made.

Existing source views are immutable captured text, not a live editor.
There is no filesystem watcher: changed files require re-analysis.
Repeating analysis with identical inputs and tools reuses the snapshot.
The [testing guide](testing.md) walks through these steps using the examples.

## Operate through the CLI

Save CLI analysis to the **same directory the server uses**:

```powershell
.\.venv\Scripts\python.exe -m codeform analyze examples/payment-service --store .codeform/demo --output .codeform/exports/payment
```

Reload the UI to discover snapshots written by another CLI process. The CLI's
`--store` defaults to `.codeform` in its current working directory; it does not
automatically inherit the running server's `--data-dir`.

The exported `bundle.json` is the portable analysis artifact. The store's
`snapshot_*.json` files are persistence records that wrap bundles with
creation metadata; use an export, rather than that wrapper, for validation
and UI import.

```powershell
.\.venv\Scripts\python.exe -m codeform validate .codeform/exports/payment/bundle.json
.\.venv\Scripts\python.exe -m codeform compare before/bundle.json after/bundle.json
.\.venv\Scripts\python.exe -m codeform --help
.\.venv\Scripts\python.exe -m codeform analyze --help
.\.venv\Scripts\python.exe -m codeform serve --help
```

`--output` writes the bundle, Markdown report, Mermaid architecture and
sequence diagrams, and any unchecked Lean candidates. Existing export files
with those names are overwritten; choose a different output directory when
keeping a history. CLI failures return a nonzero exit code.

## Data, export, backup, and restore

The selected data directory contains:

| File | Contents |
| --- | --- |
| `snapshot_<id>.json` | Creation time and the immutable analysis bundle, including captured source. |
| `snapshot_<id>.annotations.json` | Review statuses, notes, author, and update times for that snapshot. |
| `*.tmp` | Temporary atomic-write files; an interrupted write may leave one behind. |

UI JSON exports contain the bundle, **not review annotations**. Markdown and
Mermaid exports are generated views. Accepted task exports include that
finding's review note. Back up the entire data directory to preserve all
snapshots and reviews.

Stop the server before making a consistent backup. For the demo directory:

```powershell
$backupName = 'codeform-demo-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.zip'
Compress-Archive -LiteralPath .codeform/demo -DestinationPath $backupName
```

On macOS/Linux:

```bash
tar -czf codeform-demo-backup.tar.gz -C .codeform demo
```

Restore into a new directory, preserving the original until checked:

```powershell
Expand-Archive -LiteralPath codeform-demo-20261022-120000.zip -DestinationPath .codeform/restored
.\.venv\Scripts\python.exe -m codeform serve --data-dir .codeform/restored/demo
```

Substitute the actual backup filename. On macOS/Linux:

```bash
mkdir -p .codeform/restored
tar -xzf codeform-demo-backup.tar.gz -C .codeform/restored
.venv/bin/python -m codeform serve --data-dir .codeform/restored/demo
```

Check snapshot selection and a saved review note after restoration.
Imported bundles retain their original repository path; on another machine
you can inspect captured evidence, but analyze the new local repository path
to create fresh snapshots for further editing.

For a fresh session, start with an unused directory such as
`--data-dir .codeform/fresh`. This preserves existing history without deleting
anything. No snapshot-deletion UI exists in this release.

Runtime environments and `.codeform/` are ignored by Git. Exported source may
contain inline secrets even though common credential files are excluded.
Keep backups and exports in a location appropriate for the target code.

## Updates and verification

Stop the server, back up the data directory, inspect local Git changes, and
pull the new code:

```powershell
git status --short
git pull --ff-only
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Restart with the same workspace and data directory. The version, implementation
hash, and Python version participate in snapshot identity, so an analyzer
upgrade may create new snapshots for otherwise identical source.

The current validator supports schema `1.0.0`; there is no automated migration
framework. Retain backups and check future release notes before upgrading.

If Python was uninstalled or the checkout moved and `.venv` no longer works,
create a new local environment (for example `.venv-new`) and run the app with
that environment's Python. Virtual environments are machine-local and should
not be copied between computers.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| `python` not found or older than 3.11 | Install a current Python, then recreate the local environment. On Windows, `py -3 -m venv --without-pip .venv` can use the Python launcher. |
| pip setup fails | Use `--without-pip`; the app and core tests need no packages. |
| `No module named codeform` | Change to the cloned checkout and use its `.venv` Python. |
| PowerShell blocks a helper script | Use the explicit `.venv\Scripts\python.exe -m codeform ...` commands; no execution-policy change is needed. |
| Address already in use / Windows socket error | Check the listener and choose another `--port`; stop the identified code-form process only if appropriate. |
| Health check works but browser looks stale | Reload the page. After a restart, reload also refreshes the local request token. |
| Repository is outside the allowed workspace | Restart with a suitable common-parent `--workspace`. |
| No Python source found | Choose a Python repo or subdirectory; other language adapters are not implemented. |
| File/repository exceeds analysis limits | Select a smaller directory. Limits are 2,000 eligible files, 256 KB per file, and 16 MB total. Skipped files are recorded in the bundle. |
| Analysis queue is full | Wait for active jobs; at most four queued/running jobs are accepted, using two workers. |
| CLI result is missing from the UI | Match `--store` to server `--data-dir`, then reload. |
| Cannot write snapshots or reviews | Check the selected data directory's permissions and free disk space. |
| Invalid imported bundle / hash or range mismatch | Import an unmodified exported `bundle.json`, not a persistence wrapper. Re-export from the source instance if needed. |
| Snapshot identifier collision | The ID already exists with different content. Keep both artifacts separately and investigate; immutable snapshots are not overwritten. |
| Review note is absent in an imported bundle | Bundle exports omit annotations. Restore the full data-directory backup to preserve reviews. |
| Some snapshots are absent from the list | Invalid or unreadable store records are skipped. Retain the files and compare against a known-good backup. |
| Git commit is missing | Install Git and analyze a committed Git checkout. Non-Git directories still support source analysis. |
| Missing module relationships | The adapter resolves explicit Python names; runtime wiring and dynamic dispatch remain unknown. |
| Lean file contains `sorry` | Expected: it is a proposed, unchecked statement, never a completed proof. |

Analysis failures are shown in the UI. The terminal prints startup information;
routine HTTP request logging is disabled. For debugging, reproduce the same
repository with the CLI, retain its error, and run the core tests in `.venv`.
