$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $repo "launch-desktop.vbs"))) {
  $repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
$lnk = Join-Path $env:USERPROFILE "Desktop\SuperVideoGenerator.lnk"
$vbs = Join-Path $repo "launch-desktop.vbs"
$icon = Join-Path $repo "apps\desktop\icon.ico"
if (-not (Test-Path $icon)) { throw "Missing icon: $icon" }
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut($lnk)
$s.TargetPath = $vbs
$s.WorkingDirectory = $repo
$s.WindowStyle = 7
$s.Description = "SuperVideoGenerator Desktop"
$s.IconLocation = "$icon,0"
$s.Save()
Write-Host "Shortcut: $lnk"
Write-Host "Icon: $($s.IconLocation)"
