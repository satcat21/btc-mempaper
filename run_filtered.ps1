# PowerShell script to run Gunicorn with filtered logging
# This filters out static meme requests from the console output

Write-Host "🚀 Starting Mempaper with filtered logging..." -ForegroundColor Green

# Run Gunicorn and filter out lines containing "/static/memes/"
& python -m gunicorn -c gunicorn.conf.py mempaper_app:app 2>&1 | Where-Object { $_ -notmatch "/static/memes/" }

# Alternative: Save to filtered log file
# & python -m gunicorn -c gunicorn.conf.py mempaper_app:app 2>&1 | Where-Object { $_ -notmatch "/static/memes/" } | Tee-Object -FilePath "filtered_gunicorn.log"
