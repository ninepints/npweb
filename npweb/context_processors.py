from django.conf import settings


def analytics(request):
    return {'enable_analytics': settings.ENABLE_ANALYTICS}
