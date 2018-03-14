#!/usr/bin/env python

"""
main.py -- Udacity conference server-side Python App Engine
    HTTP controller handlers for memcache & task queue access

"""


import webapp2
from google.appengine.api import app_identity
from google.appengine.api import mail
from conference import ConferenceApi

from models import Speaker

import random


class SetAnnouncementHandler(webapp2.RequestHandler):

    def get(self):
        """Set Announcement in Memcache."""
        ConferenceApi._cacheAnnouncement()
        self.response.set_status(204)


class SetFeaturedSpeaker(webapp2.RequestHandler):
    # Using post seems to be triggered more often?
    def post(self):
        """Set the featured speaker in Memcache"""
        ConferenceApi._cacheFeaturedSpeaker(self.request.get('sessionKey'))


class SendConfirmationEmailHandler(webapp2.RequestHandler):

    def post(self):
        """Send email confirming Conference creation."""
        mail.send_mail(
            'noreply@%s.appspotmail.com' % (
                app_identity.get_application_id()),     # from
            self.request.get('email'),                  # to
            'You created a new Conference!',            # subj
            'Hi, you have created a following '         # body
            'conference:\r\n\r\n%s' % self.request.get(
                'conferenceInfo')
        )


app = webapp2.WSGIApplication([
    ('/crons/set_announcement', SetAnnouncementHandler),
    ('/tasks/send_confirmation_email', SendConfirmationEmailHandler),
    ('/tasks/set_featured_speaker', SetFeaturedSpeaker)
], debug=True)
