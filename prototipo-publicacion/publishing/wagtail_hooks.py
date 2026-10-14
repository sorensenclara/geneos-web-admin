from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from .models import Plan, PublishJob


class PlanViewSet(SnippetViewSet):
    model = Plan
    icon = "tag"
    menu_label = "Planes y precios"
    list_display = ["name", "price", "impl", "site", "live"]
    add_to_admin_menu = True


class PublishJobViewSet(SnippetViewSet):
    model = PublishJob
    icon = "upload"
    menu_label = "Publicaciones"
    list_display = ["site", "status", "release", "trigger", "started", "finished"]
    add_to_admin_menu = True
    inspect_view_enabled = True


register_snippet(PlanViewSet)
register_snippet(PublishJobViewSet)
