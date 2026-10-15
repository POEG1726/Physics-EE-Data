param(
    [Parameter(Mandatory = $true)]
    [string]$ScopeIp,
    [string]$OutFile = "./rg179-5m-SHORT.csv",
    [int]$WaitSeconds = 0,
    [switch]$KeepRemoteFile
)

$ErrorActionPreference = "Stop"

$base = "http://$ScopeIp"
$csvName = "usr_wf_data.csv"

function Invoke-ScopePost {
    param([hashtable]$Body)

    Invoke-WebRequest `
        -Uri "$base/device_read_write.php" `
        -Method POST `
        -Body $Body `
        -ContentType "application/x-www-form-urlencoded; charset=UTF-8"
}

Write-Host "Requesting CSV generation from $ScopeIp ..."

$generateBody = @{
    cmd = '{"cmd":"WFCSV?","type":"ds","to":"127.0.0.1"}'
    action = "excutescpicmds"
}

$generateResponse = Invoke-ScopePost -Body $generateBody
Write-Host $generateResponse.Content

Write-Host "Waiting $WaitSeconds seconds for waveform file ..."
Start-Sleep -Seconds $WaitSeconds

Write-Host "Downloading $csvName to $OutFile ..."
Invoke-WebRequest -Uri "$base/web_img/$csvName" -OutFile $OutFile

$downloaded = Get-Item -LiteralPath $OutFile
Write-Host "Downloaded $($downloaded.Length) bytes."

if (-not $KeepRemoteFile) {
    Write-Host "Deleting remote temporary file ..."
    $deleteBody = @{
        file = $csvName
        action = "delete_wavebinfile"
    }
    Invoke-ScopePost -Body $deleteBody | Out-Null
}

Write-Host "Done."
