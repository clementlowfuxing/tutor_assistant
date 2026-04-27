"""WSGI entry point for PythonAnywhere."""
import sys
import os
from dotenv import load_dotenv

project_home = '/home/clement93low/tutor_assistant'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

load_dotenv(os.path.join(project_home, '.env'))

from app import app as application
