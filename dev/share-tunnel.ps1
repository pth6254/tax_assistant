# Opens this PC's service (http://localhost:3001) to the internet through a Cloudflare quick tunnel.
# The printed https://….trycloudflare.com address changes every time this starts; share the new one.
# Keep this window open while friends use the service. Ctrl+C closes the link.
# Before running: Docker services up (./dev/docker-up-wsl.sh backend frontend in WSL) and Ollama running.
$exe = @("C:\Program Files (x86)\cloudflared\cloudflared.exe", "C:\Program Files\cloudflared\cloudflared.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $exe) { Write-Error "cloudflared not found: winget install --id Cloudflare.cloudflared -e"; exit 1 }
try { Invoke-WebRequest -UseBasicParsing http://localhost:3001/api/health/ready -TimeoutSec 5 | Out-Null }
catch { Write-Error "The service is not ready on http://localhost:3001. Start Docker services first."; exit 1 }
& $exe tunnel --no-autoupdate --url http://localhost:3001
