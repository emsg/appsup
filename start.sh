# python manage.py collectstatic
uwsgi --http :8000 --socket :8888 --chdir `pwd` --module django_wsgi &
