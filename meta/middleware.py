from google.appengine.api import users
from google.appengine.ext import ndb
from meta.models import User

class GaeAuthenticationMiddleware(object):
  def process_request(self, request):
    user = users.get_current_user()
    if not user:
        return
    q = User.query(User.user_id==user.user_id())
    user_instance = q.get()
    if not user_instance:
      user_instance = User(user_id=user.user_id(), username=user.nickname(),
                           email=user.email())
      user_instance.put()
    request.user = user_instance
