from django.conf.urls import include, url
from django.contrib import admin
from django.views.generic import TemplateView

from datareturn.views import (AuthorizeOpenHumansView, TokenLoginView,
                              UserTokensView, UserTokensCSVView)

urlpatterns = [
    # Redirect URI for completing Open Humans OAuth2 data export process.
    url(r'^open_humans_complete/$', AuthorizeOpenHumansView.as_view()),

    url(r'^admin/user_tokens/?$', UserTokensView.as_view(),
        name='admin_user_tokens'),
    url(r'^admin/user_tokens_csv/?$', UserTokensCSVView.as_view(),
        name='admin_user_tokens_csv'),
    url(r'^admin/', include(admin.site.urls)),

    url(r'^$',
        TemplateView.as_view(template_name='datareturn/home.html'),
        name='home'),
    url(r'^account/', include('allauth.urls')),
    url(r"^token_login/(?P<uidb36>[0-9A-Za-z]+)-(?P<token>.+)/$",
        TokenLoginView.as_view(), name='token_login'),
    url(r'^token_login_fail/?$',
        TemplateView.as_view(template_name='datareturn/token_login_fail.html'),
        name='token_login_fail'),
]
