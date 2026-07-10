# herdr-resurrect — one-shot pane-program restore, fired once per herdr server start.
#
# Invoked (with the call operator `&`, so its `return`s stay local) from the pwsh
# profile inside herdr panes. herdr has no post-restore hook and, on Windows, is a
# manually-launched app with no login autostart — so the login scheduled task's
# `autorestore` poller only covers herdr opened within its window. This covers the
# other case: herdr launched any time later. It detects a *new* herdr server
# instance via the default-session socket's timestamp and runs `restore` once,
# detached, so panes fill even when the poller window has already elapsed.
#
# `restore` only fills idle panes and never double-launches, so a redundant run
# (this trigger plus the poller, or two panes racing) is harmless.

if ($env:HERDR_ENV -ne '1') { return }   # only inside a herdr pane

$sock = Join-Path $env:APPDATA 'herdr\herdr.sock'
if (-not (Test-Path $sock)) { return }

# Key on the socket's write time: recreated on each server (re)start, so a new
# herdr instance yields a new key and this fires exactly once per start.
$key = (Get-Item $sock).LastWriteTime.Ticks.ToString()
$markerDir = Join-Path $env:LOCALAPPDATA 'herdr-resurrect'
$marker = Join-Path $markerDir 'autorestore-server.marker'
try {
    if ((Test-Path $marker) -and
        ((Get-Content -Raw -LiteralPath $marker -ErrorAction Stop).Trim() -eq $key)) {
        return   # already restored for this server instance
    }
    New-Item -ItemType Directory -Force -Path $markerDir -ErrorAction Stop | Out-Null
    # Claim the marker *before* launching (restore is idempotent) to blunt the
    # race when several panes' profiles load at once during layout restore.
    Set-Content -LiteralPath $marker -Value $key -NoNewline -ErrorAction Stop
} catch {
    return
}

$cli = Join-Path $PSScriptRoot 'cli.py'
if (-not (Test-Path $cli)) { return }
$pyexe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pyexe) { return }
$pyw = Join-Path (Split-Path $pyexe) 'pythonw.exe'
$run = if (Test-Path $pyw) { $pyw } else { $pyexe }

# Detached + hidden so pane startup is never blocked by a restore pass.
Start-Process -FilePath $run -ArgumentList @("`"$cli`"", 'restore') -WindowStyle Hidden
