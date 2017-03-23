from zope.interface import Interface
from zope import schema

from collective.portlet.portlet_calendar import PloneMessageFactory as _
from plone.app.textfield import RichText
from plone.theme.interfaces import IDefaultPloneLayer

class IThemeSpecific(IDefaultPloneLayer):
    """Marker interface that defines a Zope 3 browser layer.
       If you need to register a viewlet only for the
       "Weekday portlet" this interface must be its layer
    """

class IPortletCalendar(Interface):
    """
    This interface defines the portlet_calendar html record on the registry
    """

    header = schema.TextLine(
        title=_(u"Title", default=u"Title"),
        description=_(u"portlet_title", default=u"Title of the portlet."),
        required=False)
    
    portlet_calendar_html = schema.Text(
        title=_(u"portlet_calendar_html", default=u"Portlet Calendar HTML"),
        description=_(u"portlet_calendar_html_description", default=u"Paste here the integration HTML provided by Portlet Calendar"),
        required=True)
    

    