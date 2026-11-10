param(
    [ValidateSet('start', 'stop', 'status')]
    [string]$Action = 'start',
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$demoWindowsRoot = $PSScriptRoot.Replace('\', '/')
$demoResolvedPath = & wsl -d Ubuntu --exec wslpath -a $demoWindowsRoot
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve the project path in Ubuntu.' }
$demoLinuxRoot = $demoResolvedPath.Trim()
$demoPython = '/home/hxrdbvss/miniconda3/envs/mlops-lab/bin/python'
& wsl -d Ubuntu --exec $demoPython "$demoLinuxRoot/manage_demo.py" $Action
if ($LASTEXITCODE -ne 0) { throw 'Demo command failed. Check logs in .runtime.' }
if ($Action -eq 'start' -and -not $NoBrowser) {
    Start-Process 'http://localhost:8501'
}
