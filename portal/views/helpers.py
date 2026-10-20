from django.core.paginator import Paginator
from django.http import Http404


def paginate(request, queryset, per_page=25):
    page = Paginator(queryset, per_page).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    page.query = params.urlencode()
    return page


def csv_safe(value):
    """Neutralise spreadsheet formula injection in exported cells."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def get_scoped_or_404(queryset, pk):
    try:
        return queryset.get(pk=pk)
    except queryset.model.DoesNotExist:
        raise Http404("Not found")
