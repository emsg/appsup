# python manage.py collectstatic
uwsgi --http :9000 --socket :9999 --chdir `pwd` --module django_wsgi &
