# 创建 seed-agent 桌面快捷方式（桌面 + 开始菜单）。
param(
  [string]$Repo = (Split-Path $PSScriptRoot -Parent)
)

$node = Get-Command node -ErrorAction Stop
$cli = Join-Path $Repo 'src\cli.ts'
$config = Join-Path $Repo 'seed.config.json'
if (-not (Test-Path $cli)) { throw "cli not found: $cli" }
if (-not (Test-Path $config)) { throw "config not found: $config (先 cp seed.config.example.json seed.config.json)" }

$shell = New-Object -ComObject WScript.Shell
$locations = @(
  [Environment]::GetFolderPath('Desktop'),
  (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs')
)

foreach ($dir in $locations) {
  $path = Join-Path $dir 'seed-agent.lnk'
  $shortcut = $shell.CreateShortcut($path)
  $shortcut.TargetPath = $node.Source
  $shortcut.Arguments = "`"$cli`" desktop `"$config`""
  $shortcut.WorkingDirectory = $Repo
  $shortcut.Description = 'seed-agent · Super-agent Console'
  $edge = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
  if (Test-Path $edge) { $shortcut.IconLocation = "$edge,0" }
  $shortcut.Save()
  Write-Host "created: $path"
}