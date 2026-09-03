from pathlib import Path

from pathlib import Path
from django.conf import settings
from django.http import HttpResponse
from django.views import View


class ReactAppView(View):
    def get(self, request, *args, **kwargs):
        index_path = Path(settings.BASE_DIR) / 'apps' / 'web' / 'static' / 'web' / 'index.html'
        if not index_path.exists():
            return HttpResponse(
                'React frontend is not built. Run "npm run build" in the frontend directory.',
                status=503,
                content_type='text/plain',
            )
        response = HttpResponse(index_path.read_text(encoding='utf-8'))
        response['Cache-Control'] = 'no-store, max-age=0'
        return response


class ServiceWorkerView(View):
    """Expose the built worker at the origin root so it can control SPA routes."""
    def get(self, request, *args, **kwargs):
        worker_path = Path(settings.BASE_DIR) / 'apps' / 'web' / 'static' / 'web' / 'sw.js'
        if not worker_path.exists():
            return HttpResponse('Service worker is unavailable.', status=404, content_type='text/plain')
        response = HttpResponse(worker_path.read_text(encoding='utf-8'), content_type='application/javascript')
        response['Service-Worker-Allowed'] = '/'
        response['Cache-Control'] = 'no-cache'
        return response
