#!/usr/bin/env bash
# Primera vez: crea el entorno, la base local, importa el contenido actual y crea tu usuario.
# Después, para volver a entrar: scripts/iniciar.sh  (solo levanta el servidor)
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
if [ ! -d .venv ]; then
  echo "→ Creando el entorno de Python (.venv)…"
  "$PY" -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
fi
[ -f .env ] || cp .env.example .env

if [ ! -f var/db.sqlite3 ]; then
  echo "→ Creando la base de datos local…"
  .venv/bin/python manage.py migrate -v0
  echo "→ Importando el contenido actual de las webs (sitios, páginas, planes, preguntas, comparador)…"
  .venv/bin/python manage.py inicializar
  echo "→ Creá tu usuario de administradora (acceso total a todos los sitios):"
  .venv/bin/python manage.py createsuperuser
fi

echo "→ Abrí http://localhost:8000/admin/  (Ctrl+C para cerrar)"
.venv/bin/python manage.py runserver 8000
