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

### Sessions

The Implementation of the Session kind was done in line with
what was previously implemented with the Conference Object. I 
followed the same logic, with some minor changes as required for
the use of the TimeProperty in the Session, which calls for the 
use of a time object from the datetime module. I ended up saving the 
urlsafe version of the conference key for each session inside of the 
session to allow for greater ease in using the endpoint methods in the explorer.

The sessionKey and websafeConfKey could theoretically be removed in order
to further secure the application if it were going into deployment. Since 
all sessions are keyed as being the children of given conferences, the 
conference keys can be accessed through calling the parent on the entity's key.

The speaker remains in the session since it is not a parent or child to 
any given conference. I am currently looking at Implementing the speaker
in a different manner based on the ndb [KeyProperty][7]. This would allow for the
use of a many to many relationship, however it would also require a serious
bit of refactoring and a great breaking of things. 

[7]: http://stackoverflow.com/questions/24392270/many-to-many-relationship-in-ndb

### Speaker

The speaker entity was created later on in the process of construction
to facilitate greater ease in working with the getFeaturedSpeaker
method. Session keys were saved to allow for easy access to the Session
and Conference entities associated with each speaker. 

The featuredSpeaker implementation was done through the use of a BooleanField
and the logic associated with its assignment works to ensure that
only one featuredSpeaker should be named at a given time.

### Queries
- **Workshop/7pm ( getSpecialQuerySessions) :**
    I found that due to the issues arising with the use of multiple 
    inequalities in queries to the datastore, simply querying the
    database would not work. Only one inequality comparison can be 
    used per query. 
    Instead of trying to establish a workaround with
    an elaborate gql query (as I've often had to in MySQL and Postgres),
    I found that it was much easier to use a list comprehension as the
    secondary filter for the query after the primary query had been called.
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

Now to see about implementing the front end...

[8]: https://discussions.udacity.com/t/localhost-getconferencecreated-error/38247/2