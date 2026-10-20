# TestFlow first-time setup (Windows PowerShell). Safe to re-run: it never deletes db.sqlite3.
# If activation is blocked, run once:  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py check
python manage.py makemigrations accounts portal   # creates the migration files (first run only does real work)
python manage.py migrate
Write-Host ""
Write-Host "Next: python manage.py createsuperuser   then   python manage.py runserver" -ForegroundColor Green
