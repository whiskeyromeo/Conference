#!/usr/bin/env python

"""
main.py -- Udacity conference server-side Python App Engine
    HTTP controller handlers for memcache & task queue access

$Id$

created by wesc on 2014 may 24

"""

__author__ = 'wesc+api@google.com (Wesley Chun)'

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
    def post(self):
        """Set the featured speaker and associated logic"""
        # Get the current featured speaker if such exists
        cf_speaker = Speaker.query(Speaker.featuredSpeaker == True).get()
        speaker = Speaker.query(Speaker.name==self.request.get('speaker')).get()
        if not cf_speaker:
            speaker.featuredSpeaker = True
            speaker.put()
        else:
            # Flip a coin to determine whether speakership transfers to the new speaker
            outcome = random.randrange(2)
            if outcome == 0:
                # Heads, the incoming speaker is the new featuredSpeaker
                cf_speaker.featuredSpeaker = False
                speaker.featuredSpeaker = True
                cf_speaker.put()
                speaker.put()
            
        
        
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
