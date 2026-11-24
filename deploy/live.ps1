# Hosted demo from this laptop: RASID on port 8045, published through a Cloudflare quick tunnel (HTTPS).
# Needs RASID_PASSWORD in .env (judges sign in with it) and cloudflared (winget install Cloudflare.cloudflared).
# The public link is printed by cloudflared ("https://....trycloudflare.com"); it changes if this script restarts.
$root = Split-Path $PSScriptRoot
if (-not (Select-String -Path "$root\.env" -Pattern '^RASID_PASSWORD=\S' -Quiet)) { throw 'Set RASID_PASSWORD in .env first' }
$cloudflared = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cloudflared) { $cloudflared = 'C:\Program Files (x86)\cloudflared\cloudflared.exe' }
$env:RASID_GUARDIAN_REMOTE = '1'
$server = Start-Process -PassThru -NoNewWindow -WorkingDirectory $root -FilePath "$root\.venv\Scripts\python.exe" `
  -ArgumentList '-m', 'uvicorn', 'rasid.api:app', '--port', '8045', '--proxy-headers'  # cloudflared connects from 127.0.0.1, uvicorn's default trusted proxy
try { & $cloudflared tunnel --no-autoupdate --url http://localhost:8045 }
finally { Stop-Process -Id $server.Id -ErrorAction SilentlyContinue }
