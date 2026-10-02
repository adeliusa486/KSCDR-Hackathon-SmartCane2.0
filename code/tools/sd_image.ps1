# Smart cane - read-only raw image of the Pi's SD card, run on the Windows laptop.
#
# Needs administrator rights (raw disk access). The disk handle is opened with
# GENERIC_READ only, so this script cannot write to the card. It refuses to run
# unless the disk number, size and bus type all match what you expect, and it
# refuses to overwrite an existing image.
#
# The SHA-256 is computed from the bytes read off the card. Check the image
# afterwards with Get-FileHash: equal hashes prove the file holds what was read.
#
#   Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File "<this file>" -DiskNumber 1 -ExpectedBytes 31914983424 -Out "E:\...\backups\sd_2026-10-02.img"'
#
# Progress and the result go to <Out>.log.

param(
  [Parameter(Mandatory)][int]$DiskNumber,
  [Parameter(Mandatory)][long]$ExpectedBytes,
  [Parameter(Mandatory)][string]$Out
)

$ErrorActionPreference = 'Stop'
$Log = "$Out.log"
function log($msg) { "$(Get-Date -Format 'HH:mm:ss.fff')  $msg" | Tee-Object -FilePath $Log -Append }

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class RawDisk {
  [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
  public static extern SafeFileHandle CreateFile(string name, uint access, uint share,
      IntPtr security, uint disposition, uint flags, IntPtr template);
}
'@

$ok = $false
try {
  log "START disk=$DiskNumber expected=$ExpectedBytes out=$Out"

  $d = Get-Disk -Number $DiskNumber
  log "disk: '$($d.FriendlyName)' bus=$($d.BusType) size=$($d.Size) style=$($d.PartitionStyle) boot=$($d.IsBoot) system=$($d.IsSystem)"
  if ($d.Size -ne $ExpectedBytes) { throw "size $($d.Size) != expected $ExpectedBytes" }
  if ($d.BusType -ne 'USB')       { throw "bus type $($d.BusType) is not USB" }
  if ($d.IsBoot -or $d.IsSystem)  { throw "disk $DiskNumber is a boot or system disk" }
  if (Test-Path $Out)             { throw "$Out already exists, refusing to overwrite" }

  $GENERIC_READ = [uint32]2147483648
  $SHARE_RW = [uint32]3          # FILE_SHARE_READ | FILE_SHARE_WRITE
  $OPEN_EXISTING = [uint32]3
  $SEQUENTIAL = [uint32]0x08000000
  $h = [RawDisk]::CreateFile("\\.\PhysicalDrive$DiskNumber", $GENERIC_READ, $SHARE_RW,
                             [IntPtr]::Zero, $OPEN_EXISTING, $SEQUENTIAL, [IntPtr]::Zero)
  if ($h.IsInvalid) { throw "CreateFile failed, Win32 error $([Runtime.InteropServices.Marshal]::GetLastWin32Error())" }

  $src = New-Object IO.FileStream($h, [IO.FileAccess]::Read, 1)
  $partial = "$Out.partial"
  $dst = New-Object IO.FileStream($partial, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read, 1MB)
  $sha = [Security.Cryptography.SHA256]::Create()

  # Raw disk reads must be whole sectors. 4 MiB chunks, and the card size is a
  # multiple of 512, so the last short read is too.
  $chunk = 4MB
  $buf = New-Object byte[] $chunk
  $done = [long]0
  $t0 = Get-Date
  $nextPct = 5
  while ($done -lt $ExpectedBytes) {
    $want = [int][Math]::Min([long]$chunk, $ExpectedBytes - $done)
    $n = $src.Read($buf, 0, $want)
    if ($n -le 0) { throw "read returned $n at offset $done" }
    [void]$sha.TransformBlock($buf, 0, $n, $null, 0)
    $dst.Write($buf, 0, $n)
    $done += $n
    $pct = [Math]::Floor(100.0 * $done / $ExpectedBytes)
    if ($pct -ge $nextPct) {
      $s = ((Get-Date) - $t0).TotalSeconds
      log ("{0,3}%  {1} bytes  {2:N1} MB/s" -f $pct, $done, ($done / 1MB / $s))
      $nextPct += 5
    }
  }
  [void]$sha.TransformFinalBlock($buf, 0, 0)
  $dst.Flush($true); $dst.Close(); $src.Close()
  $hash = -join ($sha.Hash | ForEach-Object { $_.ToString('x2') })

  $len = (Get-Item $partial).Length
  if ($len -ne $ExpectedBytes) { throw "image is $len bytes, expected $ExpectedBytes" }
  Rename-Item $partial (Split-Path $Out -Leaf)
  $s = ((Get-Date) - $t0).TotalSeconds
  log ("read {0} bytes in {1:N0} s" -f $done, $s)
  log "SHA256 $hash"
  log "DONE"
  $ok = $true
}
catch {
  log "FAILED: $($_.Exception.Message)"
}
finally {
  if ($dst) { $dst.Dispose() }
  if ($src) { $src.Dispose() }
}

if (-not $ok) { Read-Host "Imaging failed, see $Log. Press Enter to close" }
