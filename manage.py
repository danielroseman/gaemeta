#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gaemeta.settings")
    os.environ.setdefault("APPLICATION_ID", "gaemeta")
    PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
    #sys.path.insert(0, os.path.join(PROJECT_DIR, 'google_appengine'))
    sys.path.insert(0, 'C:/Program Files (x86)/Google/google_appengine')
    # sys.path.insert(0, 'C:/Program Files (x86)/Google/google_appengine/lib')
    #sys.path.insert(0, os.path.join(PROJECT_DIR, 'google_appengine/lib'))
    #sys.path.insert(0, os.path.join(PROJECT_DIR, 'lib'))
    #print sys.path
    #import wrapper_util
    import dev_appserver
    dev_appserver.fix_sys_path()
    sys.path.insert(0, PROJECT_DIR)
    # GAE inserts django 1.4 into path, we want to use our own version.
    #sys.path = [p for p in sys.path if 'django' not in sys.path]

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
