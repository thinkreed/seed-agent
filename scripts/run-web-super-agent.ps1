# Start DSH Web harness with Super-agent, configured for Bailian.
# Usage: powershell -File scripts/run-web-super-agent.ps1 [-Port 4780] [-NoOpen] [-Repo <path>]
param(
  [int]$Port = 4780,
  [switch]$NoOpen,
  [string]$Repo
)

$ErrorActionPreference = 'Stop'
if (-not $Repo) { $Repo = (Get-Location).Path }
$dsh = $Repo + '\dsh'
$node = $env:USERPROFILE + '\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe'
if (-not (Test-Path $node)) { throw "node runtime not found: $node" }
if (-not (Test-Path ($dsh + '\apps\cli\lib\bin.js'))) { throw "dsh not built: $dsh" }

$credsPath = $Repo + '\seed.env'
Write-Output "creds=$credsPath"
if (Test-Path $credsPath) {
  foreach ($line in Get-Content $credsPath) {
    if ($line -match '^([A-Z_]+)=(.+)$') {
      Set-Item -Path ('Env:' + $Matches[1]) -Value $Matches[2].Trim()
    }
  }
}
if (-not $env:BAILIAN_API_KEY) { throw 'BAILIAN_API_KEY missing in seed.env' }

$env:DSH_HOME = $dsh + '\apps\desktop\.desktop-build\sa-web-home'
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue

$cliArgs = @(
  ($dsh + '\apps\cli\lib\bin.js'),
  '--profile', 'web',
  '--patch', ($Repo + '\config\bailian.patch.yml'),
  '--patch', ($Repo + '\sa-web.patch.yml'),
  '--port', "$Port"
)
if ($NoOpen) { $cliArgs += '--no-open' }
& $node @cliArgs