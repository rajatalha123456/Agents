from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.users.urls")),
    path("api/assets/", include("apps.assets.urls")),
    path("api/cash-flows/", include("apps.cashflows.urls")),
    path("api/", include("apps.forecasts.urls")),
    path("api/ai/", include("apps.ai_agent.urls")),
]
