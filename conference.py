#!/usr/bin/env python

"""
conference.py -- conference server-side Python App Engine API;
    uses Google Cloud Endpoints

"""



from datetime import datetime
from datetime import time

import json
import endpoints

from protorpc import messages
from protorpc import message_types
from protorpc import remote

from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.ext import ndb

from models import ConflictException
from models import Profile
from models import ProfileMiniForm
from models import ProfileForm
from models import StringMessage
from models import BooleanMessage

from models import Conference
from models import ConferenceForm
from models import ConferenceForms
from models import ConferenceQueryForm
from models import ConferenceQueryForms

from models import TeeShirtSize

from models import SessionForms
from models import Session
from models import SessionForm
from models import SessionQueryForm
from models import SessionQueryForms

from models import Speaker
from models import SpeakerForm
from models import SpeakerForms

from settings import WEB_CLIENT_ID
from settings import ANDROID_CLIENT_ID
from settings import IOS_CLIENT_ID
from settings import ANDROID_AUDIENCE

from utils import getUserId

EMAIL_SCOPE = endpoints.EMAIL_SCOPE
API_EXPLORER_CLIENT_ID = endpoints.API_EXPLORER_CLIENT_ID
MEMCACHE_ANNOUNCEMENTS_KEY = "RECENT_ANNOUNCEMENTS"
ANNOUNCEMENT_TPL = ('Last chance to attend! The following conferences '
                    'are nearly sold out: %s')

FEATURED_SPEAKER_TPL = ('Featured Speaker: %s')
MEMCACHE_FS_KEY = "FEATURED_SPEAKER"

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

DEFAULTS = {
    "city": "Default City",
    "maxAttendees": 0,
    "seatsAvailable": 0,
    "topics": ["Default", "Topic"],
}

OPERATORS = {
    'EQ':   '=',
            'GT':   '>',
            'GTEQ': '>=',
            'LT':   '<',
            'LTEQ': '<=',
            'NE':   '!='
}

FIELDS = {
    'CITY': 'city',
            'TOPIC': 'topics',
            'MONTH': 'month',
            'MAX_ATTENDEES': 'maxAttendees',
}

SESS_FIELDS = {
    'TYPE': 'typeOfSession',
    'NAME': 'name',
    'HIGHLIGHTS': 'highlights',
    'SPEAKER': 'speaker',
    'DURATION': 'duration',
    'START': 'startTime'
}


# IF the request contains path or querystring arguments, cannot use a
# simple Message class. Instead you must use a ResourceContainer class.

CONF_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1, required=True),
)

CONF_POST_REQUEST = endpoints.ResourceContainer(
    ConferenceForm,
    websafeConferenceKey=messages.StringField(1, required=True),
)

SESS_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConfKey=messages.StringField(1, required=True)
)

SPEAKER_CONF_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    speaker=messages.StringField(1, required=True),
    websafeConfKey=messages.StringField(2, required=True)
)

SESS_SPEAKER_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    speaker=messages.StringField(1, required=True)
)

SESS_TYPE_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConfKey=messages.StringField(1, required=True),
    sessionType=messages.StringField(2, required=True)
)

DATE_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    startDate=messages.StringField(1, required=True)
)

WISHLIST_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    sessionKey=messages.StringField(1, required=True)
)


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


@endpoints.api(name='conference', version='v1', audiences=[ANDROID_AUDIENCE],
               allowed_client_ids=[
                   WEB_CLIENT_ID, API_EXPLORER_CLIENT_ID, ANDROID_CLIENT_ID, IOS_CLIENT_ID],
               scopes=[EMAIL_SCOPE])
class ConferenceApi(remote.Service):
    """Conference API v0.1"""


#----- Session objects -------------------------------------

    # Copy a session object object to the SessionForm
    def _copySessionToForm(self, sess, displayName=None):
        """Copy relevant fields from Session to SessionForm"""
        sf = SessionForm()
        for field in sf.all_fields():
            if hasattr(sess, field.name):
                # Convert date to date string, copy others
                if field.name.endswith('date'):
                    setattr(sf, field.name, str(getattr(sess, field.name)))
                elif field.name.endswith('Time'):
                    setattr(sf, field.name, str(getattr(sess, field.name)))
                elif field.name.endswith('duration'):
                    setattr(sf, field.name, str(getattr(sess, field.name)))
                else:
                    setattr(sf, field.name, getattr(sess, field.name))
            if field.name == "websafeConfKey":
                setattr(sf, field.name, sess.key.parent().urlsafe())
            elif field.name == "sessionKey":
                setattr(sf, field.name, sess.key.urlsafe())
        if displayName:
            setattr(sf, 'displayName', displayName)
        sf.check_initialized()
        return sf

    # Copy the speaker entity to a SpeakerForm for display
    def _copySpeakerToForm(self, speaker):
        sf = SpeakerForm()
        for field in sf.all_fields():
            if hasattr(speaker, field.name):
                setattr(sf, field.name, str(getattr(speaker, field.name)))
        sf.check_initialized()
        return sf

    def _createSessionObject(self, request):
        """Create or update Session object, returning SessionForm/request."""
        # Get the user saved in session
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        if not request.name:
            raise endpoints.BadRequestException(
                "Session 'name' field required")
        
        c_key = ndb.Key(urlsafe=request.websafeConfKey)

        # Check that the name is unique within the conference
        name_check = Session.query(ancestor=c_key)
        name_check = name_check.filter(Session.name==request.name).get()
        
        if name_check:
            raise endpoints.BadRequestException(
                "Entity with name '%s' already exists" % request.name)


        # Check that the conference exists
        conf = c_key.get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conf with key: %s' % request.websafeConferenceKey)

        # Check that the user is the conference organizer
        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the organizer may update the conference')

        # Copy SessionForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name)
                for field in request.all_fields()}
        
        # Delete unnecessary fields from the form
        del data['displayName']
        del data['websafeConfKey'] 
        del data['sessionKey']
        
        # Convert date from string into Date object;
        if data['date']:
            data['date'] = datetime.strptime(
                data['date'][:10], "%Y-%m-%d").date()

        # Convert times from string into Time objects
        if data['startTime']:
            data['startTime'] = datetime.strptime(
                data['startTime'][:5], "%H:%M").time()
        if data['duration']:
            try:
                datetime.strptime(
                    data['duration'][:5], "%H:%M").time()
            except:
                raise endpoints.BadRequestException("Duration Must be in 'HH:MM' format")
            
        s_id = Session.allocate_ids(size=1, parent=c_key)[0]
        s_key = ndb.Key(Session, s_id, parent=c_key)

        data['key'] = s_key
        
        if data['speaker']:
            print 'In createSession, there is a speaker...'
            # Check to see if the speaker already exists
            speaker = Speaker.query(Speaker.name == data['speaker']).get()

            # If the speaker doesn't exist, create a Speaker entity for them    
            if not speaker:
                speaker_id = Speaker.allocate_ids(size=1)[0]
                speaker_key = ndb.Key(Speaker, speaker_id)
                speaker = Speaker()
                speaker.populate(
                    key=speaker_key,
                    name=data['speaker']
                )
                
                speaker.put()
            else:
                speaker_key = speaker.key
            
        
            # Set the session speaker to the speaker's urlsafe key
            data['speaker'] = speaker_key.urlsafe()
            
            #Put the session in the database
            Session(**data).put()
            
            # Use the TaskQueue to check whether the new session's
            # speaker should be the next featured speaker.
            taskqueue.add(
                params={'sessionKey': s_key.urlsafe()},
                url='/tasks/set_featured_speaker'
            )
            
        else:
            #Put the session in the database
            Session(**data).put()

        return request
    
    
    @staticmethod
    def _cacheFeaturedSpeaker(session_key):
        """Assign Featured Speaker to memcache; used by getFeaturedSpeaker"""
        # Use the urlsafe key to grab the session key
        session = ndb.Key(urlsafe=session_key).get()
        # Set the key for the memcache based on the confKey
        featured = 'fs_' + str(session.key.parent().urlsafe())     
        print 'In cacheFeaturedSpeaker'
        # Get all of the sessions for the conference
        sessions = Session.query(ancestor=session.key.parent()).fetch()
        count = 0
        # Iterate through the sessions to find the speaker with the most sessions
        for sess in sessions:
            spk_sess = Session.query(ancestor=session.key.parent()).filter(Session.speaker==sess.speaker)
            spk_count = spk_sess.count()
            if spk_count > count:
                count = spk_count
                # Save the speaker and sessions for the speaker with the most
                featured_speaker = sess.speaker
                fs_sessions = spk_sess
        # Grab the speaker
        speaker = ndb.Key(urlsafe=featured_speaker).get()
        # Set the speaker name and their sessions in a string
        fs_data = {}
        fs_data['name'] = speaker.name
        fs_data['sessions'] = []
        for sess in fs_sessions:
            fs_data['sessions'].append(sess.name)
        mem_val = json.dumps(fs_data)
        # Set the created json string in memcache
        memcache.set(key=featured, value=fs_data)
        
    @endpoints.method(CONF_GET_REQUEST, StringMessage,
                      path='conference/{websafeConferenceKey}/getFeaturedSpeaker',
                      http_method='GET',
                      name='getFeaturedSpeaker')
    def getFeaturedSpeaker(self, request):
        fs_conf = 'fs_' + str(request.websafeConferenceKey)
        return StringMessage(data=json.dumps(memcache.get(fs_conf)) or 'No featured speaker found.')
        

    # Task 3 - Additional Queries - Get All speakers
    @endpoints.method(message_types.VoidMessage, SpeakerForms,
                      path='getAllSpeakers',
                      http_method='GET',
                      name='getAllSpeakers')
    def getAllSpeakers(self, request):
        """Get all speakers using the speaker entity(Allows for checking featuredSpeaker)"""
        speakers = Speaker.query().fetch()
        return SpeakerForms(
            items=[self._copySpeakerToForm(speaker) for speaker in speakers]
        )

    # Session Implementation - Create Session
    @endpoints.method(SessionForm, SessionForm, path='session',
                      http_method='POST', name='createSession')
    def createSession(self, request):
        """Create a new session."""
        return self._createSessionObject(request)

    # Session Implementation - Get Sessions for Conference
    @endpoints.method(SESS_GET_REQUEST, SessionForms,
                      path='conference/sessions/{websafeConfKey}',
                      http_method='GET', name='getConferenceSessions')
    def getConferenceSessions(self, request):
        """ Return requested sessions (by websafeConfKey)"""
        c_key = ndb.Key(urlsafe=request.websafeConfKey)
        conf = c_key.get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conf found with key: %s' % request.websafeConfKey)
        # Get all of the sessions associated with the key
        sessions = Session.query(ancestor=c_key)
        # Populate a SessionForm for each session
        return SessionForms(
            items=[self._copySessionToForm(sess) for sess in sessions]
        )

    # Format filters for SessionQuery
    def _formatSessionFilters(self, filters):
        """Parse, check validity and format user supplied filters."""
        formatted_filters = []
        inequality_field = None

        for f in filters:
            filtr = {field.name: getattr(f, field.name)
                     for field in f.all_fields()}

            try:
                # Use the globals SESS_FIELDS and OPERATORS
                # to choose filters
                filtr["field"] = SESS_FIELDS[filtr["field"]]
                filtr["operator"] = OPERATORS[filtr["operator"]]
            except KeyError:
                raise endpoints.BadRequestException(
                    "Filter contains invalid field or operator.")

            # Every operation except "=" is an inequality
            if filtr["operator"] != "=":
                # check if inequality operation has been used in previous filters
                # disallow the filter if inequality was performed on a different field before
                # track the field on which the inequality operation is
                # performed
                if inequality_field and inequality_field != filtr["field"]:
                    raise endpoints.BadRequestException(
                        "Inequality filter is allowed on only one field.")
                else:
                    inequality_field = filtr["field"]

            formatted_filters.append(filtr)
        return (inequality_field, formatted_filters)

    # Adds filters to SessionQuery
    def _getSessionQuery(self, request):
        """Return formatted query from submitted filters"""
        q = Session.query()
        inequality_filter, filters = self._formatSessionFilters(
            request.filters)

        # if exists sort on inequality filter first
        if not inequality_filter:
            q = q.order(Session.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Session.name)

        for filtr in filters:
            formatted_query = ndb.query.FilterNode(
                filtr["field"], filtr["operator"], filtr["value"])
            q = q.filter(formatted_query)
        return q

    # Task 3 - Additional Queries - Query of Session based on user params
    @endpoints.method(SessionQueryForms, SessionForms,
                      path='querySessions',
                      http_method='POST',
                      name='querySessions')
    def querySessions(self, request):
        """Query for sessions based on user-specified filters"""
        sessions = self._getSessionQuery(request)

        return SessionForms(
            items=[self._copySessionToForm(sess) for sess in sessions]
        )

    # Session Implementation - Sessions by Type at a given Conference
    @endpoints.method(SESS_TYPE_REQUEST, SessionForms,
                      path='conference/sessions/{websafeConfKey}/{sessionType}',
                      http_method='GET',
                      name='getConferenceSessionsByType')
    def getConferenceSessionsByType(self, request):
        """Query Sessions In a conference by type"""
        c_key = ndb.Key(urlsafe=request.websafeConfKey)
        conf = c_key.get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conf found with key: %s' % request.websafeConfKey)
        q = Session.query(ancestor=c_key)
        q = q.filter(Session.typeOfSession == request.sessionType)
        return SessionForms(
            items=[self._copySessionToForm(sess) for sess in q]
        )
    
    # Task 3 - Additional Query - All Conferences For Speaker
    @endpoints.method(SESS_SPEAKER_REQUEST, ConferenceForms,
                      path='getAllConferencesBySpeaker',
                      http_method='GET',
                      name='getAllConferencesBySpeaker')
    def getAllConferencesBySpeaker(self, request):
        """Query for conferences by speaker using the Speaker entity"""
        q = Speaker.query()
        q = q.filter(Speaker.name == request.speaker).get()

        if not q:
            raise endpoints.BadRequestException(
                "No speaker by the name of '%s'" % request.speaker)
        
        spk_sessions = Session.query().filter(Session.speaker==q.key.urlsafe())
        confs = []
            
        for sess in spk_sessions:
            conf = sess.key.parent().get()
            if conf not in confs:
                confs.append(conf)

        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, '') for conf in confs]
        )

    # Task 3 - Additional Query - Sessions by Speaker at Conference
    @endpoints.method(SPEAKER_CONF_REQUEST, SessionForms,
                      path='getConferenceSessionsBySpeaker',
                      http_method='GET',
                      name='getConferenceSessionsBySpeaker')
    def getConferenceSessionsBySpeaker(self, request):
        """Query for sessions in a particular conference by speaker using the Session entity"""
        speaker = Speaker.query(Speaker.name==request.speaker).get()
        if not speaker:
            raise endpoints.BadRequestException(
                "No speaker by the name of '%s'" % request.speaker)

        c_key = ndb.Key(urlsafe=request.websafeConfKey)
        q = Session.query(ancestor=c_key)
        q = q.filter(Session.speaker == speaker.key.urlsafe())
        if not q:
            raise endpoints.BadRequestException(
                "No record with that key")

        return SessionForms(
            items=[self._copySessionToForm(sess) for sess in q]
        )

    # Session Implementation - Sessions By Speaker
    @endpoints.method(SESS_SPEAKER_REQUEST, SessionForms,
                      path='getAllSessionsForSpeaker',
                      http_method='GET',
                      name='getAllSessionsForSpeaker')
    def getAllSessionsForSpeaker(self, request):
        """Retrieve all sessions for a given speaker using the Speaker entity"""
        speaker = Speaker.query()
        speaker = speaker.filter(Speaker.name == request.speaker).get()
        
        if not speaker:
            raise endpoints.BadRequestException(
                "No speaker by the name of '%s'" % request.speaker)
        sessions = Session.query().filter(Session.speaker==speaker.key.urlsafe())

        return SessionForms(
            items=[self._copySessionToForm(sess) for sess in sessions]
        )

    # Task 3 - Additional Query - Sessions By Date
    @endpoints.method(DATE_REQUEST, SessionForms,
                      path='getSessionsBeforeDate',
                      http_method='GET',
                      name='getSessionsBeforeDate')
    def getSessionsBeforeDate(self, request):
        """Get all sessions before a given date"""
        if not request.startDate:
            raise endpoints.BadRequestException(
                "Session 'startDate' is required for query")
        startDate = datetime.strptime(request.startDate[:10], "%Y-%m-%d")
        q = Session.query()
        q = q.filter(Session.date < startDate)
        q = q.filter(Session.date != None)
        return SessionForms(
            items=[self._copySessionToForm(sess) for sess in q]
        )

    # Task 3 - Additional Query - Conferences By date
    @endpoints.method(DATE_REQUEST, ConferenceForms,
                      path='getConferencesBeforeDate',
                      http_method='GET',
                      name='getConferencesBeforeDate')
    def getConferencesBeforeDate(self, request):
        """Get all Conferences starting before a given date"""
        if not request.startDate:
            raise endpoints.BadRequestException(
                "Session 'startDate' is required for query")

        startDate = datetime.strptime(request.startDate[:10], "%Y-%m-%d")

        q = Conference.query()
        q = q.filter(Conference.startDate < startDate)
        q = q.filter(Conference.startDate != None)
        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, '') for conf in q]
        )

    def _checkType(self, session):
        val = str(getattr(session, 'typeOfSession'))
        if val == 'workshop':
            return True
        return False

    # Task 3 - Workshop/7pm Query Problem
    @endpoints.method(message_types.VoidMessage, SessionForms,
                      path='getSpecialQuerySessions',
                      http_method='GET',
                      name='getSpecialQuerySessions')
    def getSpecialQuerySessions(self, request):
        """Query for sessions which are not workshops and
        where the startTime is before 7pm"""
        checkTime = '19:00'
        time = datetime.strptime(checkTime[:5], "%H:%M").time()
        q = Session.query()
        q = q.filter(Session.startTime < time)
        q = q.filter(Session.startTime != None)
        sessions = [i for i in q if not self._checkType(i)]

        return SessionForms(
            items=[self._copySessionToForm(sess) for sess in sessions]
        )

    # Get Sessions created by User
    @endpoints.method(message_types.VoidMessage, SessionForms,
                      path='getSessionsCreated',
                      http_method='POST', name='getSessionsCreated')
    def getSessionsCreated(self, request):
        """Return sessions created by user."""
        # check that user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # create an ancestor query for all key matches to the user
        sessions = Session.query(ancestor=ndb.Key(Profile, user_id))
        prof = ndb.Key(Profile, user_id).get()

        # return set of ConferenceForm objects per Conference
        return SessionForms(
            items=[self._copySessionToForm(sess, getattr(
                prof, 'displayName')) for sess in sessions]
        )


# - - - - Session WishList - - - - - -

    @ndb.transactional(xg=True)
    def _wishListAddition(self, request, add=True):
        """Handles addition/removal of selected session from the user's wishlist"""
        retval = None
        prof = self._getProfileFromUser()

        s_key = request.sessionKey
        sess = ndb.Key(urlsafe=s_key).get()

        if not sess:
            raise endpoints.NotFoundException(
                'No session found with key: %s' % s_key
            )

        # Add
        if add:
            # Check if user already added the Session
            if s_key in prof.sessionKeysToAttend:
                raise ConflictException(
                    "You have already added this session to your list."
                )

            prof.sessionKeysToAttend.append(s_key)
            retval = True
        # Remove
        else:
            # Check if the Session is in the user's wishlist
            if s_key in prof.sessionKeysToAttend:
                # Remove from wishlist
                prof.sessionKeysToAttend.remove(s_key)
                retval = True
            else:
                retval = False
        # Write back to datastore and return
        prof.put()

        return BooleanMessage(data=retval)

    # Wishlist Implementation - Add Session to Wishlist
    @endpoints.method(WISHLIST_REQUEST, BooleanMessage,
                      path='wishlist/add/{sessionKey}',
                      http_method='POST',
                      name='addSessionToWishlist')
    def addSessionToWishlist(self, request):
        """Add session to user's wishlist"""
        return self._wishListAddition(request)

    # Wishlist Implementation - Get all Sessions in Wishlist
    @endpoints.method(message_types.VoidMessage, SessionForms,
                      path='sessions/wishlist',
                      http_method='GET',
                      name='getSessionsInWishlist')
    def getSessionsInWishlist(self, request):
        """Get user's wishlist of sessions"""
        prof = self._getProfileFromUser()
        sess_keys = [ndb.Key(urlsafe=s_key)
                     for s_key in prof.sessionKeysToAttend]
        sessions = ndb.get_multi(sess_keys)

        return SessionForms(items=[self._copySessionToForm(sess) for sess in sessions])

    # Wishlist Implementation - Delete session from Wishlist
    @endpoints.method(WISHLIST_REQUEST, BooleanMessage,
                      path='wishlist/remove/{sessionKey}',
                      http_method='POST',
                      name='deleteSessionInWishlist')
    def deleteSessionInWishlist(self, request):
        """Remove a session from the user's wishlist"""
        return self._wishListAddition(request, add=False)


# - - - Conference objects - - - - - - - - - - - - - - - - -

    def _copyConferenceToForm(self, conf, displayName):
        """Copy relevant fields from Conference to ConferenceForm."""
        cf = ConferenceForm()
        for field in cf.all_fields():
            if hasattr(conf, field.name):
                # convert Date to date string; just copy others
                if field.name.endswith('Date'):
                    setattr(cf, field.name, str(getattr(conf, field.name)))
                else:
                    setattr(cf, field.name, getattr(conf, field.name))
            elif field.name == "websafeKey":
                setattr(cf, field.name, conf.key.urlsafe())
        if displayName:
            setattr(cf, 'organizerDisplayName', displayName)
        cf.check_initialized()
        return cf

    def _createConferenceObject(self, request):
        """Create or update Conference object, returning ConferenceForm/request."""
        # preload necessary data items
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        if not request.name:
            raise endpoints.BadRequestException(
                "Conference 'name' field required")

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name)
                for field in request.all_fields()}
        del data['websafeKey']
        del data['organizerDisplayName']

        # add default values for those missing (both data model & outbound
        # Message)
        for df in DEFAULTS:
            if data[df] in (None, []):
                data[df] = DEFAULTS[df]
                setattr(request, df, DEFAULTS[df])

        # convert dates from strings to Date objects; set month based on
        # start_date
        print '----ABOUT TO PRINT STARTDATE-----'
        if data['startDate']:
            print '  startDate', data['startDate']
            data['startDate'] = datetime.strptime(
                data['startDate'][:10], "%Y-%m-%d").date()
            data['month'] = data['startDate'].month
        else:
            data['month'] = 0
        if data['endDate']:
            data['endDate'] = datetime.strptime(
                data['endDate'][:10], "%Y-%m-%d").date()

        # set seatsAvailable to be same as maxAttendees on creation
        if data["maxAttendees"] > 0:
            data["seatsAvailable"] = data["maxAttendees"]
        # generate Profile Key based on user ID and Conference
        # ID based on Profile key get Conference key from ID
        p_key = ndb.Key(Profile, user_id)
        c_id = Conference.allocate_ids(size=1, parent=p_key)[0]
        c_key = ndb.Key(Conference, c_id, parent=p_key)
        data['key'] = c_key
        data['organizerUserId'] = request.organizerUserId = user_id

        # create Conference, send email to organizer confirming
        # creation of Conference & return (modified) ConferenceForm
        Conference(**data).put()
        taskqueue.add(params={'email': user.email(),
                              'conferenceInfo': repr(request)},
                      url='/tasks/send_confirmation_email'
                      )
        return request

    # Update a Conference
    @ndb.transactional()
    def _updateConferenceObject(self, request):
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name)
                for field in request.all_fields()}

        # update existing conference
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        # check that conference exists
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)

        # check that user is owner
        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the owner can update the conference.')

        # Not getting all the fields, so don't create a new object; just
        # copy relevant fields from ConferenceForm to Conference object
        for field in request.all_fields():
            data = getattr(request, field.name)
            # only copy fields where we get data
            if data not in (None, []):
                # special handling for dates (convert string to Date)
                if field.name in ('startDate', 'endDate'):
                    data = datetime.strptime(data, "%Y-%m-%d").date()
                    if field.name == 'startDate':
                        conf.month = data.month
                # write to Conference object
                setattr(conf, field.name, data)
        conf.put()
        prof = ndb.Key(Profile, user_id).get()
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))

    # Create a Conference endpoint
    @endpoints.method(ConferenceForm, ConferenceForm, path='conference',
                      http_method='POST', name='createConference')
    def createConference(self, request):
        """Create new conference."""
        return self._createConferenceObject(request)

    # Update a Conference endpoint
    @endpoints.method(CONF_POST_REQUEST, ConferenceForm,
                      path='conference/{websafeConferenceKey}',
                      http_method='PUT', name='updateConference')
    def updateConference(self, request):
        """Update conference w/provided fields & return w/updated info."""
        return self._updateConferenceObject(request)

    @endpoints.method(CONF_GET_REQUEST, ConferenceForm,
                      path='conference/{websafeConferenceKey}',
                      http_method='GET', name='getConference')
    def getConference(self, request):
        """Return requested conference (by websafeConferenceKey)."""
        # get Conference object from request; bail if not found
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)
        prof = conf.key.parent().get()
        # return ConferenceForm
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))

    # Get conferences created by User
    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='getConferencesCreated',
                      http_method='POST', name='getConferencesCreated')
    def getConferencesCreated(self, request):
        """Return conferences created by user."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # create ancestor query for all key matches for this user
        confs = Conference.query(ancestor=ndb.Key(Profile, user_id))
        prof = ndb.Key(Profile, user_id).get()
        # return set of ConferenceForm objects per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(
                conf, getattr(prof, 'displayName')) for conf in confs]
        )

    def _getQuery(self, request):
        """Return formatted query from the submitted filters."""
        q = Conference.query()
        inequality_filter, filters = self._formatFilters(request.filters)

        # If exists, sort on inequality filter first
        if not inequality_filter:
            q = q.order(Conference.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Conference.name)

        for filtr in filters:
            if filtr["field"] in ["month", "maxAttendees"]:
                filtr["value"] = int(filtr["value"])
            formatted_query = ndb.query.FilterNode(
                filtr["field"], filtr["operator"], filtr["value"])
            q = q.filter(formatted_query)
        return q

    def _formatFilters(self, filters):
        """Parse, check validity and format user supplied filters."""
        formatted_filters = []
        inequality_field = None

        for f in filters:
            filtr = {field.name: getattr(f, field.name)
                     for field in f.all_fields()}

            try:
                filtr["field"] = FIELDS[filtr["field"]]
                filtr["operator"] = OPERATORS[filtr["operator"]]
            except KeyError:
                raise endpoints.BadRequestException(
                    "Filter contains invalid field or operator.")

            # Every operation except "=" is an inequality
            if filtr["operator"] != "=":
                # check if inequality operation has been used in previous filters
                # disallow the filter if inequality was performed on a different field before
                # track the field on which the inequality operation is
                # performed
                if inequality_field and inequality_field != filtr["field"]:
                    raise endpoints.BadRequestException(
                        "Inequality filter is allowed on only one field.")
                else:
                    inequality_field = filtr["field"]

            formatted_filters.append(filtr)
        return (inequality_field, formatted_filters)

    @endpoints.method(ConferenceQueryForms, ConferenceForms,
                      path='queryConferences',
                      http_method='POST',
                      name='queryConferences')
    def queryConferences(self, request):
        """Query for conferences."""
        conferences = self._getQuery(request)

        # need to fetch organiser displayName from profiles
        # get all keys and use get_multi for speed
        organisers = [(ndb.Key(Profile, conf.organizerUserId))
                      for conf in conferences]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        # return individual ConferenceForm object per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, names[conf.organizerUserId]) for conf in
                   conferences]
        )


# - - - Profile objects - - - - - - - - - - - - - - - - - - -

    def _copyProfileToForm(self, prof):
        """Copy relevant fields from Profile to ProfileForm."""
        # copy relevant fields from Profile to ProfileForm
        pf = ProfileForm()
        for field in pf.all_fields():
            if hasattr(prof, field.name):
                # convert t-shirt string to Enum; just copy others
                if field.name == 'teeShirtSize':
                    setattr(pf, field.name, getattr(
                        TeeShirtSize, getattr(prof, field.name)))
                else:
                    setattr(pf, field.name, getattr(prof, field.name))
        pf.check_initialized()
        return pf

    def _getProfileFromUser(self):
        """Return user Profile from datastore, creating new one if non-existent."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')

        # get Profile from datastore
        user_id = getUserId(user)
        p_key = ndb.Key(Profile, user_id)
        profile = p_key.get()
        # create new Profile if not there
        if not profile:
            profile = Profile(
                key=p_key,
                displayName=user.nickname(),
                mainEmail=user.email(),
                teeShirtSize=str(TeeShirtSize.NOT_SPECIFIED),
            )
            profile.put()

        return profile      # return Profile

    def _doProfile(self, save_request=None):
        """Get user Profile and return to user, possibly updating it first."""
        # get user Profile
        prof = self._getProfileFromUser()

        # if saveProfile(), process user-modifyable fields
        if save_request:
            for field in ('displayName', 'teeShirtSize'):
                if hasattr(save_request, field):
                    val = getattr(save_request, field)
                    if val:
                        setattr(prof, field, str(val))
                        # if field == 'teeShirtSize':
                        #    setattr(prof, field, str(val).upper())
                        # else:
                        #    setattr(prof, field, val)
                        prof.put()

        # return ProfileForm
        return self._copyProfileToForm(prof)

    @endpoints.method(message_types.VoidMessage, ProfileForm,
                      path='profile', http_method='GET', name='getProfile')
    def getProfile(self, request):
        """Return user profile."""
        return self._doProfile()

    @endpoints.method(ProfileMiniForm, ProfileForm,
                      path='profile', http_method='POST', name='saveProfile')
    def saveProfile(self, request):
        """Update & return user profile."""
        return self._doProfile(request)


# - - - Announcements - - - - - - - - - - - - - - - - - - - -

    @staticmethod
    def _cacheAnnouncement():
        """Create Announcement & assign to memcache; used by
        memcache cron job & putAnnouncement().
        """
        confs = Conference.query(ndb.AND(
            Conference.seatsAvailable <= 5,
            Conference.seatsAvailable > 0)
        ).fetch(projection=[Conference.name])

        if confs:
            # If there are almost sold out conferences,
            # format announcement and set it in memcache
            announcement = ANNOUNCEMENT_TPL % (
                ', '.join(conf.name for conf in confs))
            memcache.set(MEMCACHE_ANNOUNCEMENTS_KEY, announcement)
        else:
            # If there are no sold out conferences,
            # delete the memcache announcements entry
            announcement = ""
            memcache.delete(MEMCACHE_ANNOUNCEMENTS_KEY)

        return announcement

    @endpoints.method(message_types.VoidMessage, StringMessage,
                      path='conference/announcement/get',
                      http_method='GET', name='getAnnouncement')
    def getAnnouncement(self, request):
        """Return Announcement from memcache."""
        return StringMessage(data=memcache.get(MEMCACHE_ANNOUNCEMENTS_KEY) or "")


# - - - Registration - - - - - - - - - - - - - - - - - - - -

    @ndb.transactional(xg=True)
    def _conferenceRegistration(self, request, reg=True):
        """Register or unregister user for selected conference."""
        retval = None
        prof = self._getProfileFromUser()  # get user Profile

        # check if conf exists given websafeConfKey
        # get conference; check that it exists
        wsck = request.websafeConferenceKey
        conf = ndb.Key(urlsafe=wsck).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        # register
        if reg:
            # check if user already registered otherwise add
            if wsck in prof.conferenceKeysToAttend:
                raise ConflictException(
                    "You have already registered for this conference")

            # check if seats avail
            if conf.seatsAvailable <= 0:
                raise ConflictException(
                    "There are no seats available.")

            # register user, take away one seat
            prof.conferenceKeysToAttend.append(wsck)
            conf.seatsAvailable -= 1
            retval = True

        # unregister
        else:
            # check if user already registered
            if wsck in prof.conferenceKeysToAttend:

                # unregister user, add back one seat
                prof.conferenceKeysToAttend.remove(wsck)
                conf.seatsAvailable += 1
                retval = True
            else:
                retval = False

        # write things back to the datastore & return
        prof.put()
        conf.put()
        return BooleanMessage(data=retval)

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='conferences/attending',
                      http_method='GET', name='getConferencesToAttend')
    def getConferencesToAttend(self, request):
        """Get list of conferences that user has registered for."""
        prof = self._getProfileFromUser()  # get user Profile
        conf_keys = [ndb.Key(urlsafe=wsck)
                     for wsck in prof.conferenceKeysToAttend]
        conferences = ndb.get_multi(conf_keys)

        # get organizers
        organisers = [ndb.Key(Profile, conf.organizerUserId)
                      for conf in conferences]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        # return set of ConferenceForm objects per Conference
        return ConferenceForms(items=[self._copyConferenceToForm(conf, names[conf.organizerUserId])
                                      for conf in conferences]
                               )

    @endpoints.method(CONF_GET_REQUEST, BooleanMessage,
                      path='conference/{websafeConferenceKey}',
                      http_method='POST', name='registerForConference')
    def registerForConference(self, request):
        """Register user for selected conference."""
        return self._conferenceRegistration(request)

    @endpoints.method(CONF_GET_REQUEST, BooleanMessage,
                      path='conference/{websafeConferenceKey}',
                      http_method='DELETE', name='unregisterFromConference')
    def unregisterFromConference(self, request):
        """Unregister user for selected conference."""
        return self._conferenceRegistration(request, reg=False)

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='filterPlayground',
                      http_method='GET', name='filterPlayground')
    def filterPlayground(self, request):
        """Filter Playground"""
        q = Conference.query()
        # field = "city"
        # operator = "="
        # value = "London"
        # f = ndb.query.FilterNode(field, operator, value)
        # q = q.filter(f)
        q = q.filter(Conference.city == "London")
        q = q.filter(Conference.topics == "Medical Innovations")
        q = q.filter(Conference.month == 6)

        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, "") for conf in q]
        )


api = endpoints.api_server([ConferenceApi])  # register API
