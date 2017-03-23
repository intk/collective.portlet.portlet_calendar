from setuptools import setup, find_packages
import os

version = '0.0.1'

setup(name='collective.portlet.portlet_calendar',
      version=version,
      description="A portlet which can render a calendar.",
      long_description=open("README.rst").read() + "\n" +
                       open("docs/HISTORY.txt").read(),
      # Get more strings from
      # http://pypi.python.org/pypi?%3Aaction=list_classifiers
      classifiers=[
        "Framework :: Plone",
        "Programming Language :: Python",
        ],
      keywords='portlet_calendar',
      author='Andre Goncalves',
      author_email='andre@intk.com',
      url='https://github.com/intk/collective.portlet.portlet_calendar',
      download_url='https://github.com/intk/collective.portlet.portlet_calendar/tarball/0.0.1',
      license='GPL',
      packages=find_packages(exclude=['ez_setup']),
      namespace_packages=['collective', 'collective.portlet'],
      include_package_data=True,
      zip_safe=False,
      install_requires=[
          'setuptools',
          # -*- Extra requirements: -*-
      ],
      entry_points="""
      # -*- Entry points: -*-

      [z3c.autoinclude.plugin]
      target = plone
      """,
      setup_requires=["PasteScript"],
      paster_plugins=["ZopeSkel"],
      )
