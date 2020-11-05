#!/bin/bash
export WORKON_HOME=$HOME/.virtualenvs
export VIRTUALENVWRAPPER_PYTHON=/usr/bin/python3
source /usr/local/bin/virtualenvwrapper.sh
workon cv
python /home/pi/Autolinetester/manage.py runserver 0.0.0.0:8000 --insecure >> /home/pi/Autolinetester/web.log 2>&1
