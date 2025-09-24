param([string]\)
switch (\) {
  "run"      { poetry run python manage.py runserver 0.0.0.0:8000 }
  "migrate"  { poetry run python manage.py migrate }
  "super"    { poetry run python manage.py createsuperuser }
  "lint"     { poetry run ruff check . --fix; poetry run isort .; poetry run black . }
  "collect"  { poetry run python manage.py collectstatic --noinput }
  default    { Write-Host "Usage: .\task.ps1 [run|migrate|super|lint|collect]" }
}
