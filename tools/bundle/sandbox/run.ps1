# A clean Windows (Sandbox, network off) extracts the bundle and runs it.
# Results go to C:\results (mapped, writable).
$ErrorActionPreference = "Continue"
$log = "C:\results\sandbox.log"
function Log($text) { "$(Get-Date -Format HH:mm:ss) $text" | Out-File -Append -Encoding utf8 $log }
Log "start; user $env:USERNAME; $((Get-CimInstance Win32_OperatingSystem).Caption) $((Get-CimInstance Win32_OperatingSystem).Version)"
Log "msvcp140 in System32: $(Test-Path C:\Windows\System32\msvcp140.dll); vcruntime140: $(Test-Path C:\Windows\System32\vcruntime140.dll)"
Log "python on PATH: $((Get-Command python -ErrorAction SilentlyContinue).Source)"
try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 https://huggingface.co | Out-Null; Log "network: REACHABLE" } catch { Log "network: off" }
$zip = Get-ChildItem C:\dist\pymol-copilot-*-win64.zip | Select-Object -First 1
$target = "$env:USERPROFILE\Downloads\Jürgen Müller\pymol-copilot-win64 (1)"
New-Item -ItemType Directory -Force $target | Out-Null
$t = Measure-Command { tar -xf $zip.FullName -C $target }
Log ("extracted {0} in {1:N0} s, exit {2}" -f $zip.Name, $t.TotalSeconds, $LASTEXITCODE)
$b = "$target\pymol-copilot"
$t = Measure-Command { & "$b\python\python.exe" "$b\repo\tools\bundle\check_bundle.py" *>&1 | ForEach-Object { "$_" } | Out-File -Encoding utf8 C:\results\check.log }
Log ("check_bundle exit {0} after {1:N0} s" -f $LASTEXITCODE, $t.TotalSeconds)
Log "left running after check: $(@(Get-Process lemond,llama-server -ErrorAction SilentlyContinue).Count)"
# The launcher, as a double-click starts it; JupyterLab must answer.
$launcher = Start-Process -FilePath "$b\Start PyMOL Copilot.bat" -PassThru -WindowStyle Minimized
$up = $false
foreach ($i in 1..90) {
  Start-Sleep 2
  try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://127.0.0.1:8888/api; $up = $true; Log "JupyterLab answered after $($i*2) s: $($r.Content)"; break } catch {}
}
if (-not $up) { Log "JupyterLab did not answer in 180 s" }
Get-ChildItem "$b\state" -Recurse -Directory -ErrorAction SilentlyContinue | Select-Object -First 12 | ForEach-Object { Log "state: $($_.FullName.Substring($b.Length))" }
Stop-Process -Id $launcher.Id -Force -ErrorAction SilentlyContinue
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
Log "files written outside the bundle under the profile: $((Get-ChildItem $env:USERPROFILE -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notlike "$target*" -and $_.LastWriteTime -gt (Get-Date).AddHours(-1) -and $_.FullName -notlike '*\AppData\Local\Temp\*' -and $_.FullName -notlike '*\AppData\Local\Microsoft\*' -and $_.FullName -notlike '*NTUSER*' } | Select-Object -First 15 | ForEach-Object { $_.FullName }) -join '; ')"
Log "done"
