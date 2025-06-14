"""
URL configuration for mikro_server project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import include
from .schema import schema
from kante.path import dynamicpath
from django.http import HttpResponse

t = ""
def graphql_schema(request):
    return HttpResponse(content=schema.as_str(), content_type="text/plain")


urlpatterns = [
    dynamicpath("admin/", admin.site.urls),
    dynamicpath("schema", graphql_schema),
    dynamicpath("api/", include("bridge.urls")),
]
