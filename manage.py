#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gaemeta.settings")
    PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
    import wrapper_util
    dir_path = wrapper_util.get_dir_path('wrapper_util.py', os.path.join('lib', 'ipaddr'))
    paths = wrapper_util.Paths(dir_path)
    sys.path[1:1] = paths.script_paths('dev_appserver.py')
    import yaml
    conf = yaml.load(open('app.yaml'))
    app_id = "dev~{}".format(conf['application'])
    os.environ.setdefault("APPLICATION_ID", app_id)
    from google.appengine.tools.devappserver2 import api_server
    api_server.test_setup_stubs(app_id=app_id, application_root=PROJECT_DIR, datastore_path='/var/db/gaedata/datastore.db')

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
