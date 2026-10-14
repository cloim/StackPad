param([Parameter(Mandatory=$true)][string]$Job)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$jobPath = (Resolve-Path -LiteralPath $Job).Path
$python = (Get-Command python).Source
$worker = Join-Path $PSScriptRoot 'job-worker.py'
$startup = New-CimInstance -CimClass (Get-CimClass Win32_ProcessStartup) -Property @{ ShowWindow = [uint16]0 } -ClientOnly
$result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
  CommandLine = ('"{0}" "{1}" "{2}"' -f $python, $worker, $jobPath)
  CurrentDirectory = $root
  ProcessStartupInformation = $startup
}
if ($result.ReturnValue -ne 0) { throw "WMI launch failed: $($result.ReturnValue)" }
$result | Select-Object ProcessId,ReturnValue
