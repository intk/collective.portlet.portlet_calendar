from Acquisition import aq_inner
from ComputedAttribute import ComputedAttribute
from Products.CMFCore.utils import getToolByName
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from plone.app.event.base import RET_MODE_OBJECTS
from plone.app.event.base import _prepare_range
from plone.app.event.base import expand_events
from plone.app.event.base import first_weekday
from plone.app.event.base import get_events, construct_calendar
from plone.app.event.base import localized_today, localized_now
from plone.app.event.base import start_end_query
from plone.app.event.base import wkday_to_mon1
from plone.app.event.portlets import get_calendar_url
from plone.app.portlets import PloneMessageFactory as _
from plone.app.portlets.portlets import base
from plone.app.querystring import queryparser
from plone.app.uuid.utils import uuidToObject
from plone.app.vocabularies.catalog import CatalogSource
from plone.event.interfaces import IEventAccessor
from plone.portlets.interfaces import IPortletDataProvider
from zExceptions import NotFound
from zope import schema
from zope.component.hooks import getSite
from zope.i18nmessageid import MessageFactory
from zope.interface import implementer
import calendar
import json
from bda.plone.cart import get_item_stock
from plone.event.interfaces import IOccurrence
import datetime
from Acquisition import aq_parent
from bda.plone.ticketshop.interfaces import IBuyableEvent
from plone.app.event.base import start_end_from_mode
from plone.app.event.base import RET_MODE_ACCESSORS
from plone.app.event.base import guess_date_from
from bda.plone.ticketshop.interfaces import ITicketOccurrenceData
from bda.plone.ticketshop.interfaces import ITicket
import plone.api
from plone.app.event.base import default_timezone

from zope.component import getMultiAdapter

from bda.plone.cart import readcookie, extractitems
from bda.plone.cart import get_catalog_brain

try:
    from plone.app.contenttypes.behaviors.collection import ISyndicatableCollection as ICollection  # noqa
    from plone.app.contenttypes.interfaces import IFolder
    search_base_uid_source = CatalogSource(object_provides={
        'query': [
            ICollection.__identifier__,
            IFolder.__identifier__
        ],
        'operator': 'or'
    })
except ImportError:
    search_base_uid_source = CatalogSource(is_folderish=True)
    ICollection = None

PLMF = MessageFactory('plonelocales')



def localized_date(context=None, date=None):
    """Return the current datetime localized to the default timezone.
    :param context: Context object.
    :type context: Content object
    :returns: Localized current datetime.
    :rtype: Python datetime
    """
    if not date:
        return None

    tzinfo = default_timezone(context=context, as_tzinfo=True)
    try:
        return date.replace(tzinfo=tzinfo)
    except:
        return date.replace(tzinfo=tzinfo)


class ICalendarPortlet(IPortletDataProvider):
    """A portlet displaying a calendar
    """

    state = schema.Tuple(
        title=_(u"Workflow state"),
        description=_(u"Items in which workflow state to show."),
        default=None,
        required=False,
        value_type=schema.Choice(
            vocabulary="plone.app.vocabularies.WorkflowStates")
    )

    search_base_uid = schema.Choice(
        title=_(u'portlet_label_search_base', default=u'Search base'),
        description=_(
            u'portlet_help_search_base',
            default=u'Select search base Folder or Collection to search for '
                    u'events. The URL to to this item will also be used to '
                    u'link to in calendar searches. If empty, the whole site '
                    u'will be searched and the event listing view will be '
                    u'called on the site root.'
        ),
        required=False,
        source=search_base_uid_source,
    )


@implementer(ICalendarPortlet)
class Assignment(base.Assignment):
    title = _(u'Calendar')

    # reduce upgrade pain
    state = None
    search_base = None

    def __init__(self, state=None, search_base_uid=None):
        self.state = state
        self.search_base_uid = search_base_uid

    def _uid(self):
        # This is only called if the instance doesn't have a search_base_uid
        # attribute, which is probably because it has an old
        # 'search_base' attribute that needs to be converted.
        path = self.search_base
        portal = getToolByName(self, 'portal_url').getPortalObject()
        try:
            search_base = portal.unrestrictedTraverse(path.lstrip('/'))
        except (AttributeError, KeyError, TypeError, NotFound):
            return
        return search_base.UID()
    search_base_uid = ComputedAttribute(_uid, 1)


class Renderer(base.Renderer):
    render = ViewPageTemplateFile('portlet_calendar.pt')

    _search_base = None

    @property
    def search_base(self):
        if not self._search_base:
            self._search_base = uuidToObject(self.data.search_base_uid)
        # aq_inner, because somehow search_base gets wrapped by the renderer
        return aq_inner(self._search_base)

    @property
    def search_base_path(self):
        search_base = self.search_base
        if search_base is not None:
            search_base = '/'.join(search_base.getPhysicalPath())
        return search_base

    def update(self):
        context = aq_inner(self.context)

        self.calendar_url = get_calendar_url(context, self.search_base_path)

        self.year, self.month, self.date = year, month, date = self._year_month_date_display_patch()
        self.prev_year, self.prev_month = prev_year, prev_month = (
            self.get_previous_month(year, month))
        self.next_year, self.next_month = next_year, next_month = (
            self.get_next_month(year, month))
        
        self.prev_query = '?month=%s&year=%s' % (prev_month, prev_year)
        self.next_query = '?month=%s&year=%s' % (next_month, next_year)

        self.cal = calendar.Calendar(first_weekday())

        self._ts = getToolByName(context, 'translation_service')
        self.month_name = PLMF(
            self._ts.month_msgid(month),
            default=self._ts.month_english(month)
        )

        # strftime %w interprets 0 as Sunday unlike the calendar.
        strftime_wkdays = [
            wkday_to_mon1(day) for day in self.cal.iterweekdays()
        ]

        self.weekdays = [
            PLMF(self._ts.day_msgid(day, format='s'),
                 default=self._ts.weekday_english(day, format='a'))
            for day in strftime_wkdays
        ]

    def _year_month_date_display_patch(self):
        """ Return the year, month and day to display in the calendar.
        """
        context = aq_inner(self.context)
        request = self.request

        # Try to get year and month from request
        year = request.get('year', None)
        month = request.get('month', None)
        date = request.get('date', None)

        # Or use current date
        today = localized_today(context)
        if not year:
            year = datetime.datetime.today().year
        if not month:
            month = datetime.datetime.today().month

        # try to transform to number but fall back to current
        # date if this is ambiguous
        try:
            year, month = int(year), int(month)
        except (TypeError, ValueError):
            year, month = today.year, today.month

        return year, month, date

    def year_month_display(self):
        """ Return the year and month to display in the calendar.
        """
        context = aq_inner(self.context)
        request = self.request

        # Try to get year and month from request
        year = request.get('year', None)
        month = request.get('month', None)

        # Or use current date
        today = localized_today(context)
        
        if not year:
            year = datetime.datetime.today().year
        if not month:
            month = datetime.datetime.today().month

        # try to transform to number but fall back to current
        # date if this is ambiguous
        try:
            year, month = int(year), int(month)
        except (TypeError, ValueError):
            year, month = today.year, today.month

        return year, month

    def get_previous_month(self, year, month):
        if month == 0 or month == 1:
            month, year = 12, year - 1
        else:
            month -= 1
        return (year, month)

    def get_next_month(self, year, month):
        if month == 12:
            month, year = 1, year + 1
        else:
            month += 1
        return (year, month)

    def date_events_url(self, date):
        return '%s?mode=day&date=%s' % (self.calendar_url, date)

    def _date_events_url_patch(self):
        return '%s?mode=day&date=%s&ajax_load=1' % (self.calendar_url, self.date)

    def _get_events(self):
        import urllib
        f = urllib.urlopen(self._date_events_url_patch())
        html = f.read()
        return html

    @property
    def total_items_cart(self):
        cart_items = self.get_cart_items()
        total_count = 0
        
        for uid, count, comment, coupon in cart_items:
            brain = get_catalog_brain(self.context, uid)
            if brain.portal_type == 'product':
                total_count += count

        return total_count

    def is_past(self, occ):
        try:
            occ_start_date = occ.get('start', '')
            occ_end_date = occ.get('end', '')

            if '11:00' in occ_start_date.strftime('%H:%M') and '17:00' in occ_end_date.strftime('%H:%M'):
                return False

            datetime_now = datetime.datetime.now()
            return localized_date(self.context, datetime_now) > localized_date(self.context, occ_start_date)
        except:
            return False

    def get_cart_items(self):
        cart_items = extractitems(readcookie(self.request))
        return cart_items

    def _get_occs(self):

        date = guess_date_from(self.date)

        if date:
            start, end = start_end_from_mode('day', date, self.context)
            query = {}

            #query['review_state'] = self.data.state
            
            search_base_path = self.search_base_path
            if search_base_path:
                query['path'] = {'query': search_base_path}

            list_events = []

            events = get_events(self.context, start=start, end=end, sort='start', sort_reverse=False, ret_mode=RET_MODE_OBJECTS, expand=True, **query)

            today = datetime.datetime.today().date()

            for occ in events:
                if IOccurrence.providedBy(occ):
                    occurrence_id = occ.id
                    event = aq_parent(occ)
                    occ_data = ITicketOccurrenceData(event)
                    occs = occ_data.ticket_occurrences(occurrence_id)
                    if occs:
                        occurrence_ticket = occs[0]
                        item_stock = get_item_stock(occurrence_ticket)
                        if item_stock:
                            stock = item_stock.available
                        else:
                            stock = 0

                        is_today = occ.start.date() == today

                        new_event = {
                            "start": occ.start,
                            "end": occ.end,
                            "uid": occurrence_ticket.UID(),
                            "stock": stock,
                            "is_today": is_today
                        }
                        list_events.append(new_event)
                        
                elif IBuyableEvent.providedBy(occ):
                    occ_data = ITicketOccurrenceData(occ)
                    occs = occ_data.tickets
                    if occs:
                        occurrence_ticket = occs[0]
                        item_stock = get_item_stock(occurrence_ticket)
                        if item_stock:
                            stock = item_stock.available
                        else:
                            stock = 0
                        
                        is_today = occ.start.date() == today
  
                        new_event = {
                            "start": occ.start,
                            "end": occ.end,
                            "uid": occurrence_ticket.UID(),
                            "stock": stock,
                            "is_today": is_today
                        }
                        list_events.append(new_event)
                else:
                    print 'NOT AVAILABLE'

            return list_events
        else:
            return []

    def date_query(self, date):
        query = '?month=%s&year=%s&date=%s' % (self.month, self.year, date)
        return query

    @property
    def cal_data(self):
        """Calendar iterator over weeks and days of the month to display.
        """
        context = aq_inner(self.context)
        today = localized_today(context)

        year, month = self.year_month_display()
        monthdates = [dat for dat in self.cal.itermonthdates(year, month)]

        start = monthdates[0]
        end = monthdates[-1]

        data = self.data
        query = {}
        if data.state:
            query['review_state'] = data.state

        events = []
        query.update(self.request.get('contentFilter', {}))
        search_base = self.search_base
        
        if ICollection and ICollection.providedBy(search_base):
            # Whatever sorting is defined, we're overriding it.
            query = queryparser.parseFormquery(
                search_base, search_base.query,
                sort_on='start', sort_order=None
            )

            # restrict start/end with those from query, if given.
            if 'start' in query and query['start'] > start:
                start = query['start']
            if 'end' in query and query['end'] < end:
                end = query['end']

            start, end = _prepare_range(search_base, start, end)
            query.update(start_end_query(start, end))
            events = search_base.results(
                batch=False, brains=True, custom_query=query
            )
            events = expand_events(
                events, ret_mode=RET_MODE_OBJECTS,
                start=start, end=end,
                sort='start', sort_reverse=False
            )
        else:
            search_base_path = self.search_base_path
            if search_base_path:
                query['path'] = {'query': search_base_path}
            
            #start = "2020-06-01"
            events = get_events(context, start=start, end=end,
                                ret_mode=RET_MODE_OBJECTS,
                                expand=True, **query)

        
        #today += datetime.timedelta(days=1)
        #today = datetime.date(2021, 6, 5)
        #cal_dict_start = construct_calendar(events, start=datetime.date(2020, 11, 4), end=datetime.date(2020, 11, 4))
        cal_dict = construct_calendar(events, start=today, end=end)
        #cal_dict = {}
        #cal_dict.update(cal_dict_start)
        #cal_dict.update(cal_dict_end)

        # [[day1week1, day2week1, ... day7week1], [day1week2, ...]]
        caldata = [[]]
        for dat in monthdates:
            if len(caldata[-1]) == 7:
                caldata.append([])
            date_events = None
            isodat = dat.isoformat()
            if isodat in cal_dict:
                date_events = cal_dict[isodat]

            events_string_list = []
            if date_events:
                for occ in date_events:
                    accessor = IEventAccessor(occ)
                    location = accessor.location
                    whole_day = accessor.whole_day

                    time = accessor.start.time().strftime('%H:%M')
                    # TODO: make 24/12 hr format configurable
                    events_string_list.append(
                        u'{0}{1}{2}{3}'.format(
                            accessor.title,
                            u' {0}'.format(time) if not whole_day else u'',
                            u', ' if not whole_day and location else u'',
                            u' {0}'.format(location) if location else u''
                        )
                    )
            caldata[-1].append(
                {'date': dat,
                 'day': dat.day,
                 'prev_month': dat.month < month,
                 'next_month': dat.month > month,
                 'today':
                    dat.year == today.year and
                    dat.month == today.month and
                    dat.day == today.day,
                 'date_string': u"%s-%s-%s" % (dat.year, dat.month, dat.day),
                 'events_string': u' | '.join(events_string_list),
                 'events': date_events})
        return caldata

    def get_language(self):
        """
        @return: Two-letter string, the active language code
        """
        context = self.context.aq_inner
        portal_state = getMultiAdapter((context, self.request), name=u'plone_portal_state')
        current_language = portal_state.language()
        return current_language

    def nav_pattern_options(self, year, month):
        return json.dumps({
            'url': '%s/%s/@@render-portlet?portlethash=%s&year=%s&month=%s' % (
                getSite().absolute_url(), self.get_language(),
                self.hash,
                year, month),
            'target': '#portletwrapper-%s > *' % self.hash
        })

    def _nav_pattern_options_date(self, year, month, date):
        result = json.dumps({
            'url': '%s/%s/@@render-portlet?portlethash=%s&year=%s&month=%s&date=%s' % (
                getSite().absolute_url(), self.get_language(),
                self.hash,
                year, month, date),
            'target': '#portletwrapper-%s > *' % self.hash
        })
        return result

    @property
    def hash(self):
        return self.request.form.get(
            'portlethash',
            getattr(self, '__portlet_metadata__', {}).get('hash', ''))


class AddForm(base.AddForm):
    schema = ICalendarPortlet
    label = _(u"Add Calendar Portlet")
    description = _(u"This portlet displays events in a calendar.")

    def create(self, data):
        return Assignment(state=data.get('state', None),
                          search_base_uid=data.get('search_base_uid', None))


class EditForm(base.EditForm):
    schema = ICalendarPortlet
    label = _(u"Edit Calendar Portlet")
    description = _(u"This portlet displays events in a calendar.")


    
