App Engine application for the Udacity training course.

## Products
- [App Engine][1]

## Language
- [Python][2]

## APIs
- [Google Cloud Endpoints][3]

## Setup Instructions
1. Update the value of `application` in `app.yaml` to the app ID you
   have registered in the App Engine admin console and would like to use to host
   your instance of this sample.
1. Update the values at the top of `settings.py` to
   reflect the respective client IDs you have registered in the
   [Developer Console][4].
1. Update the value of CLIENT_ID in `static/js/app.js` to the Web client ID
1. (Optional) Mark the configuration files as unchanged as follows:
   `$ git update-index --assume-unchanged app.yaml settings.py static/js/app.js`
1. Run the app with the devserver using `dev_appserver.py DIR`, and ensure it's running by visiting your local server's address (by default [localhost:8080][5].)
1. (Optional) Generate your client library(ies) with [the endpoints tool][6].
1. Deploy your application.


[1]: https://developers.google.com/appengine
[2]: http://python.org
[3]: https://developers.google.com/appengine/docs/python/endpoints/
[4]: https://console.developers.google.com/
[5]: https://localhost:8080/
[6]: https://developers.google.com/appengine/docs/python/endpoints/endpoints_tool


## Modifications

### Serving App

**Serving at :** https://striking-shadow-119316.appspot.com
**Explorer :** https://striking-shadow-119316.appspot.com/_ah/api/explorer

### Sessions

The Implementation of the Session kind was done in line with
what was previously implemented with the Conference Object. I 
followed the same logic, with some minor changes as required for
the use of the TimeProperty in the Session, which calls for the 
use of a time object from the datetime module.

The websafeConfKey and SessionKey for each session are displayed in the
SessionForm to provide for easy access to the information for use in the
queries and methods implemented in conference.py.

For the date property, the DateProperty was chosen since the only the 
date is needed. This is converted to a date object and stored in the datastore.

The duration property is set as a stringProperty since it represents a 
length of time and not a fixed point in time. A check is implemented to ensure that
the duration can be converted to a datetime object before the duration can be stored.
This allows for the use of datetime methods on the value at a future point 
so that further queries or methods involving the startTime can be implemented
(such as finding the end time of the session using [timedelta][10]). The current
setup does limit the duration to 24 hours(which seems like it would be more than 
sufficient for most presentations), however it provides an effective check to 
ensure that the representation of the time is properly formatted. Once checks are in place
to ensure the proper formatting, the check could be removed.

The startTime property was implemented as a TimeProperty since it represents
a fixed point in time. Since the spec for the project called for the 
use of both a date and startTime property in the Session entity, it made
sense to set the date under the dateProperty and the startTime under the TimeProperty
instead of combining the two as a single DateTimeProperty.

The speaker is set up to take the name of a speaker, which is traded out for
a key representing the Speaker entity which is created in the event that the 
speaker is new. If the name of the speaker exists, the existing key for the speaker
is substituted. This may cause issue if more than one speaker exists with 
the exact same name, but this might be rectified by separating the creation 
of Sessions and Speakers entirely, so that a speaker is registered before the
creation of the session and their id or urlsafe key is provided in the creation of
the session.

### Speaker

The Speaker entity was developed primarily to serve as a means
by which one could keep track of the sessions of a speaker and 
for the purpose of setting the Featured Speaker for a given Conference.

I ended up only saving the name and key of the Speaker in the entities, 
and referencing the urlsafe key of the speaker in the Session methods.
The speakers were set up independently from the Conferences 
since I felt it was likely that a speaker might be present at multiple conferences.
Speakers are also technically independent from Sessions since from what I 
understand, only one parent may be set for an entity. This prevents the Session from
being the child of both a Speaker and a Conference, which necessitates
the inclusion of the speaker field in the Session entity.

### Queries
- **Workshop/7pm ( getSpecialQuerySessions) :**
    I found that due to the issues arising with the use of multiple 
    inequalities in queries to the datastore, simply querying the
    database would not work. At least one issue with the problem involved
    the restriction on datastore queries which allows the inequality filter
    to be used on one property of the entity per query. In order to correct for this
    I chose to query the datastore with a comparison filter for the time
    and used a [list comprehension][9] to filter out the workshop type from the result
    of the datastore query. I chose the list comprehension because it is more verbose
    and easier to understand the mechanism by which the list was being filtered.
    I believe the same result could have been achieved by inverting the filtration( type != workshop first,
    time comparison second) and using a map or filter method on the result obtained
    by the initial query to the Datastore.
- **Queries by Date ( getSessionsBeforeDate, getConferencesBeforeDate) :**
    A couple of the queries I added filter the respective entities
    based on the date provided by the user
- **Queries by user choice( querySessions) :**
    The queries by user choice pretty much follow the same line as the 
    queryConferences method, using modified versions of the functions
    called by the aforementioned method.
- **Speaker Queries ( getAllSpeakers, getAllSessionsForSpeaker, getAllConferencesForSpeaker) :**
    These queries use the speaker entity to get the sessions and 
    conferences associated with the speaker name provided by the user.

## Notes

I have encountered a number of issues with using the app engine on
localhost that continue to persist, though the deployed version seems
to work without issue. Somewhere fairly recently in the process I lost
the ability to work with the explorer on the local machine and no visible
issues appear in the log. From what I have read on the [discussion boards][8] 
this may have to do with caching and hopefully time, along with some detailed
inspection, will help to resolve the issue.

Currently I feel that in many of the endpoints I am making more queries on the 
datastore than necessary and hope that with some retooling I might
be able to minimize the amount of calls and perhaps speed up the application
a bit.


[7]: http://stackoverflow.com/questions/24392270/many-to-many-relationship-in-ndb
[8]: https://discussions.udacity.com/t/localhost-getconferencecreated-error/38247/2
[9]: http://www.python-course.eu/list_comprehension.php
[10]: http://stackoverflow.com/questions/18303301/working-with-time-values-greater-than-24-hours
#### Me
Will Russell
whiskeyromeo06@gmail.com
