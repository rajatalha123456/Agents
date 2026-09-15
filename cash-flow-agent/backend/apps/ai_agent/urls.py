from django.urls import path

from .views import ChatView, WhatIfView

urlpatterns = [
    path("chat/", ChatView.as_view(), name="ai-chat"),
    path("whatif/", WhatIfView.as_view(), name="ai-whatif"),
]
