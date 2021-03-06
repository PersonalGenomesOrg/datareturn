import datetime
import os

from django.conf import settings
from django.contrib.sites.models import Site
from django.db import models
from django.utils import timezone
from django.utils.deconstruct import deconstructible

import requests

from storages.backends.s3boto import S3BotoStorage

User = settings.AUTH_USER_MODEL


class UnauthorizedTokenError(Exception):
    pass


@deconstructible
class MyS3BotoStorage(S3BotoStorage):
    """
    Adds custom method to create "long term URL" w/permission lasting a year.
    """
    def longterm_url(self, name):
        name = self._normalize_name(self._clean_name(name))
        if self.custom_domain:
            return "%s://%s/%s" % ('https' if self.secure_urls else 'http',
                                   self.custom_domain, name)
        else:
            return self.connection.generate_url(
                31540000, method='GET', bucket=self.bucket.name,
                key=self._encode_name(name), query_auth=self.querystring_auth,
                force_http=not self.secure_urls)


class DataFile(models.Model):
    user = models.ForeignKey(User)
    datafile = models.FileField(
        storage=MyS3BotoStorage(acl='private',
                                querystring_auth=True,
                                querystring_expire=239200))
    description = models.TextField(default='')

    @property
    def basename(self):
        return os.path.basename(self.datafile.name)

    def __unicode__(self):
        return ':'.join([self.user.email, self.datafile.name])


class DataLink(models.Model):
    user = models.ForeignKey(User)
    url = models.TextField(default='')
    name = models.TextField(default='')
    description = models.TextField(default='')

    def __unicode__(self):
        return ':'.join([self.user.email, self.name])


class SiteConfig(models.Model):
    """
    Site configuration, customize with additional information and descriptions.
    """
    site = models.OneToOneField(Site)
    source_name = models.TextField(default='')
    home_page_summary = models.TextField(default='', blank=True)
    data_page_intro = models.TextField(default='', blank=True)
    data_page_open_humans = models.TextField(default='', blank=True)
    data_page_data_section = models.TextField(default='', blank=True)
    invite_email_subject = models.TextField(default='', blank=True)
    invite_email_content = models.TextField(default='', blank=True)
    invite_email_postscript = models.TextField(default='', blank=True)


class OpenHumansConfig(models.Model):
    """
    Site configuration for data export to Open Humans. Only one should exist.
    """
    site = models.OneToOneField(Site)
    source_name = models.CharField(max_length=255)

    token_url = settings.OPEN_HUMANS_SERVER + '/oauth2/token/'

    @property
    def auth_url(self):
        return (settings.OPEN_HUMANS_SERVER +
                '/oauth2/authorize?client_id={}&response_type=code'.format(
                    settings.OPEN_HUMANS_CLIENT_ID) +
                '&scope=wildlife%20read%20write')

    @property
    def return_url(self):
        return '{}/study/{}/return/'.format(
            settings.OPEN_HUMANS_SERVER, self.source_name)

    @property
    def userdata_url(self):
        return '{}/api/{}/user-data/'.format(
            settings.OPEN_HUMANS_SERVER, self.source_name)

    @property
    def removal_url(self):
        return '{}/member/me/connections/'.format(settings.OPEN_HUMANS_SERVER)


class OpenHumansUser(models.Model):
    """
    Handle data for a user's Open Humans account connection.
    """
    user = models.OneToOneField(User)
    openhumans_userid = models.PositiveIntegerField(null=True)
    access_token = models.CharField(max_length=60, blank=True)
    refresh_token = models.CharField(max_length=60, blank=True)
    token_expiration = models.DateTimeField(null=True)

    def _refresh_tokens(self):
        site = Site.objects.get_current()

        response_refresh = requests.post(
            site.openhumansconfig.token_url,
            data={
                'grant_type': 'refresh_token',
                'refresh_token': self.refresh_token,
                'client_id': settings.OPEN_HUMANS_CLIENT_ID,
                'client_secret': settings.OPEN_HUMANS_CLIENT_SECRET,
            })

        if response_refresh.status_code == 401:
            raise UnauthorizedTokenError(Exception)

        token_data = response_refresh.json()

        self.access_token = token_data['access_token']
        self.refresh_token = token_data['refresh_token']
        self.token_expiration = (
            timezone.now() + datetime.timedelta(
                seconds=token_data['expires_in']))

        self.save()

    def _token_expired(self, offset=0):
        """
        True if token expired (or expires in offset seconds), otherwise False.
        """
        offset_expiration = (
            self.token_expiration - timezone.timedelta(seconds=offset))
        if timezone.now() >= offset_expiration:
            return True
        return False

    def get_access_token(self, offset=30):
        """
        Return access token fresh for at least offset seconds (default 30).
        """
        if self._token_expired(offset=30):
            self._refresh_tokens()
        return self.access_token

    def is_connected(self):
        """
        Return true if access token is working, indicating user is connected.
        """
        site = Site.objects.get_current()
        try:
            check_data = requests.get(
                site.openhumansconfig.userdata_url,
                headers={'Content-type': 'application/json',
                         'Authorization':
                         'Bearer {}'.format(self.get_access_token())})
            if check_data.status_code == 200:
                return True
        except UnauthorizedTokenError:
            return False
        return False

    def create_exported_data(self):
        """
        Return dict containing data to be exported to Open Humans 'data' field.
        """
        data = {}
        files = DataFile.objects.filter(user=self.user)
        links = DataLink.objects.filter(user=self.user)
        if files:
            data['files'] = {}
            for datafile in files:
                data['files'][datafile.basename] = datafile.datafile.storage.longterm_url(datafile.datafile.name)
        if links:
            data['links'] = {}
            for datalink in links:
                data['links'][datalink.name] = datalink.url
        return data

    def __unicode__(self):
        return '{} OpenHumans:{}'.format(self.user.email,
                                         self.openhumans_userid)


class LoggedUserEvent(models.Model):
    user = models.ForeignKey(User)
    timestamp = models.DateTimeField(auto_now_add=True)
    description = models.TextField()

    def __unicode__(self):
        return '{} {}: {}'.format(
            str(self.timestamp), self.user.username, self.description)
