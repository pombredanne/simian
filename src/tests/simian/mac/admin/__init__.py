#!/usr/bin/env python
# Copyright 2010 Google Inc. All Rights Reserved.
#

"""Top level __init__ for admin package."""




import datetime
import logging
import os
import re
import urllib

import webapp2

from google.appengine.ext.webapp import template

from simian import settings
from simian.mac.admin import xsrf
from simian.mac.common import auth


QUERY_LIMITS = [25, 50, 100, 250, 500, 1000, 2000]

DEFAULT_COMPUTER_FETCH_LIMIT = 25

MENU = [
    {'type': 'summary', 'url': '/admin', 'name': 'Summary'},

    {'type': 'search', 'url': 'javascript:simian.showSearch(); void(0);',
     'name': 'Search'},

    {'type': 'munki_packages', 'name': 'Munki Packages', 'subitems': [
        {'type': 'packages', 'url': '/admin/packages', 'name': 'Package Admin'},
        {'type': 'package_logs', 'url': '/admin/packages/logs', 'name': 'Logs'},
        {'type': 'packages_historical', 'url': '/admin/packages?historical=1',
         'name': 'Historical List'},
        {'type': 'packages_installs', 'url': '/admin/installs',
         'name': 'Installs'},
        {'type': 'packages_failures',
         'url': '/admin/installs?failures=1', 'name': 'Failures'},
        {'type': 'packages_problems', 'url': '/admin/installproblems',
         'name': 'Other Install Problems'}
    ]},

    {'type': 'apple_updates', 'name': 'Apple Updates', 'subitems': [
        {'type': 'apple_applesus', 'url': '/admin/applesus',
         'name': 'Catalog Admin'},
        {'type': 'apple_logs', 'url': '/admin/applesus/logs',
         'name': 'Logs'},
        {'type': 'apple_historical', 'url': '/admin/packages?applesus=1',
         'name': 'Historical List'},
        {'type': 'apple_installs', 'url': '/admin/installs?applesus=1',
         'name': 'Installs'},
        {'type': 'apple_failures',
         'url': '/admin/installs?applesus=1&failures=1',
         'name': 'Failures'}
    ]},

    {'type': 'manifests', 'name': 'Manifests', 'subitems': [
        {'type': 'manifests_admin', 'url': '/admin/manifest_modifications',
         'name': 'Modification Admin'},
        {'type': 'manifests_aliases', 'url': '/admin/package_alias',
         'name': 'Package Aliases'},
        {'type': 'manifest_stable', 'url': '/admin/manifest/stable',
         'name': 'View Stable'},
        {'type': 'manifest_testing', 'url': '/admin/manifest/testing',
         'name': 'View Testing'},
        {'type': 'manifest_unstable', 'url': '/admin/manifest/unstable',
         'name': 'View Unstable'}
    ]},

    {'type': 'admin_tools', 'name': 'Admin Tools', 'admin_only': True,
     'subitems': [
         {'type': 'acl_groups', 'url': '/admin/acl_groups',
          'name': 'ACL Groups'},
         {'type': 'config', 'url': '/admin/config',
          'name': 'Configuration'},
         {'type': 'ip_blacklist', 'url': '/admin/ip_blacklist',
          'name': 'IP Blacklist'},
         {'type': 'lock_admin', 'url': '/admin/lock_admin',
          'name': 'Lock Admin'},
         {'type': 'panic', 'url': '/admin/panic', 'name': 'Panic Mode'},
    ]},

    {'type': 'tags', 'url': '/admin/tags', 'name': 'Tags'},

    {'title': 'Client Reports'},

    {'type': 'broken_clients', 'url': '/admin/brokenclients',
     'name': 'Broken Clients'},
    {'type': 'diskfree', 'url': '/admin/diskfree', 'name': 'Low Disk Space'},
    {'type': 'uptime', 'url': '/admin/uptime', 'name': 'Long Uptime'},
    {'type': 'offcorp', 'url': '/admin/offcorp', 'name': 'Longest Off Corp'},
    {'type': 'loststolen', 'url': '/admin/loststolen',
     'name': 'Lost/Stolen Computers'},
    {'type': 'msu_gui_logs', 'url': '/admin/msulogsummary',
     'name': 'MSU GUI Logs'},
    {'type': 'preflight_exits', 'url': '/admin/preflightexits',
     'name': 'Preflight Exits'},
    {'type': 'usersettings_knobs', 'url': '/admin/user_settings',
     'name': 'UserSettings Knobs'}
]


class Error(Exception):
  """Base Error."""


class AdminHandler(webapp2.RequestHandler):
  """Class for Admin UI request handlers."""

  XSRF_PROTECT = False

  def handle_exception(self, *args, **kwargs):
    """Handle an exception.

    Args:
      exception: exception that was thrown
      debug_mode: True if the application is running in debug mode
    """
    # TODO(user): this could notify us...
    super(AdminHandler, self).handle_exception(*args, **kwargs)

  def IsAdminUser(self):
    """Returns True if the current user is an admin, False otherwise."""
    # NOTE(user): this is definitely not threadsafe.
    if not hasattr(self, '_is_admin'):
      self._is_admin = auth.IsAdminUser()
    return self._is_admin

  def Paginate(self, query, default_limit):
    """Returns a list of entities limited to limit, with a next_page cursor."""
    try:
      limit = int(self.request.get('limit', default_limit))
    except ValueError:
      limit = default_limit
    if limit not in QUERY_LIMITS:
      limit = default_limit

    cursor = self.request.get('page', '')
    if cursor:
      query.with_cursor(cursor)

    entities = list(query.fetch(limit))

    if len(entities) == limit:
      next_page = query.cursor()
    else:
      next_page = None

    self._page = {
        'limit': limit,
        'next_page': next_page,
        'results_count': len(entities),
    }

    return entities

  def Render(self, template_path, values, write_to_response=True):
    """Renders a template using supplied data values and returns HTML.

    Args:
      template_path: str path of template.
      values: dict of template values.
      write_to_response: bool, True to write to response.out.write().
    Returns:
      str HTML of rendered template.
    """
    path = os.path.join(
        os.path.dirname(__file__), 'templates', template_path)

    if not settings.DEV_APPSERVER:
      values['static_path'] = 'myapp/%s' % os.getenv('CURRENT_VERSION_ID')

    values['is_admin'] = self.IsAdminUser()

    values['menu'] = MENU

    if 'msg' not in values:
      values['msg'] = self.request.GET.get('msg')

    if 'report_type' not in values:
      values['report_type'] = 'undefined_report'

    if self.XSRF_PROTECT:
      values['xsrf_token'] = xsrf.XsrfTokenGenerate(values['report_type'])

    if hasattr(self, '_page'):
      values['limit'] = self._page.get('limit')
      values['next_page'] = self._page.get('next_page')
      values['results_count'] = self._page.get('results_count')
      values['limits'] = QUERY_LIMITS

      values['request_query_params'] = self.request.GET
      values['request_path'] = self.request.path

      if self._page.get('next_page'):
        # Generate next page link, replacing "page" query param with next_page.
        query_params = self.request.GET.copy()
        query_params['page'] = self._page.get('next_page')
        values['next_page_link'] = '%s?%s' % (
            self.request.path, urllib.urlencode(query_params, doseq=True))

    html = template.render(path, values)
    if write_to_response:
      self.response.out.write(html)
    return html


class UTCTZ(datetime.tzinfo):
  """tzinfo class for the UTC time zone."""

  def tzname(self, unused_dt):
    return 'UTC'

  def dst(self, unused_dt):
    return datetime.timedelta(0)

  def utcoffset(self, unused_dt):
    return datetime.timedelta(0)


def AddTimezoneToComputerDatetimes(computer):
  """Sets the tzinfo on all Computer.connected_datetimes for use with Django.

  Args:
    computer: models.Computer entity.
  Returns:
    Boolean. True if one date is today, false otherwise.
  """
  for i in xrange(0, len(computer.connection_datetimes)):
    cdt = computer.connection_datetimes[i]
    # set timezone so Django "timesince" template filter works.
    computer.connection_datetimes[i] = datetime.datetime(
        cdt.year, cdt.month, cdt.day,
        cdt.hour, cdt.minute, cdt.second,
        tzinfo=UTCTZ())


def XmlToHtml(xml):
  """Convert an XML string into an HTML DOM with styles"""
  tags = re.compile(r'\<(\/?)(\w*)([^<>]*)\>')
  html = tags.sub((r'<span class="xml_tag \2">&lt;\1<span class="xml_key">\2'
                   r'</span><span class="xml_attributes">\3</span>&gt;</span>'),
                  xml)
  html = html.replace('  ', '&nbsp;&nbsp;&nbsp;&nbsp;').replace('\n', '<br/>')
  return '<div class="xml">%s</div>' % html
