from bakery.views import Buildable404View
from django.core.handlers.base import BaseHandler


# Our 404 template depends on middleware, which Buildable404View doesn't consult before rendering
class Middleware404View(Buildable404View):
    build_path = 'err-404.html'

    def __init__(self, **kwargs):
        self.handler = BaseHandler()
        self.handler.load_middleware()
        super().__init__(**kwargs)

    def get(self, request):
        return self.handler.get_response(request)

    def get_content(self):
        response = self.get(self.request)
        if hasattr(response, 'render'):
            return response.render().content
        if hasattr(response, 'content'):
            return response.content
        raise AttributeError(
            "'%s' object has no attribute 'render' or 'content'" % response)
