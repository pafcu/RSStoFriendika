#!/usr/bin/env python
# Application to post RSS updates to Friendika
import sys
import urllib
import urllib2
import urlparse
import cPickle as pickle
import hashlib
import StringIO
import ConfigParser
import copy
import time

# External libraries
import feedparser
import mako.template as mako
import lxml.etree as etree

conf_path = 'RSStoFriendika.conf'

def tweet(server, message):
	url = server + '/api/statuses/update'
	urllib2.urlopen(url, urllib.urlencode({'status': message}))

htmltobbcode = etree.parse('htmltobbcode/HTMLtoBBCode.xslt')
htmlparser = etree.HTMLParser()
def makebbcode(html):
	return unicode(etree.parse(StringIO.StringIO(html), htmlparser).xslt(htmltobbcode))

config = ConfigParser.SafeConfigParser()
config.read(conf_path)
config_changed = False
def getconfig(config, option, valid=''):
	"""Interactively read config values"""
	global config_changed # Ugly!
	try:
		return config.get('main',option)
	except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
		config.set('main',option,raw_input('%s%s: '%(option.replace('_',' '), valid)))
		config_changed = True
		return config.get('main',option)

# Read config
old_config = copy.copy(config)
server = getconfig(config,'server').rstrip('/')
username = getconfig(config,'username')
password = getconfig(config,'password')
feeds_path = getconfig(config,'feeds_file')
# A bit of trickery to store a bool. ConfigParser.readboolean is no good because it doesn't accept "y" and "n".
store_guids = config.set('main','always_store_guid', str(getconfig(config,'always_store_guid', ' (y/N)').lower().startswith('y')))
# Handle defaults like this or a DEFAULT section is written to output config file
try:
	guids_path = config.get('main','guids_file')
except:
	guids_path = 'processed.dat'
try:
	feeds_updated = config.getfloat('main','updated')
except:
	feeds_updated = 0

if config_changed:
	reply = raw_input('Save config? (y/N): ')
	if reply.lower().startswith('y'):
		with open(conf_path, 'w') as configfile:
		    config.write(configfile)
	else:
		config = old_config

# Set up basic authentication
passman = urllib2.HTTPPasswordMgrWithDefaultRealm()
passman.add_password(None, server, username, password)
authhandler = urllib2.HTTPBasicAuthHandler(passman)
opener = urllib2.build_opener(authhandler)
urllib2.install_opener(opener)

# Try to open "database" containing already processed GUIDs
# TODO: Something more efficient and robust
try:
	with open(guids_path, 'r') as guids_file:
		processed = pickle.load(guids_file)
except:
	processed = set()

# Iterate over feed list
for line in open(feeds_path):
	if line.startswith('#'): # Skip comments
		continue

	feed_url, template_path = line.strip().split()
	feed = feedparser.parse(feed_url)

	for entry in feed['entries']:
		try:
			guid = entry['guid']
		except:
			guid = hashlib.sha256(repr(entry)).hexdigest()

		try:
			updated = time.mktime(entry['updated_parsed'])
		except KeyError:
			updated = None

		updated = False # Too many feeds lie to actually make this useful, so turn off date checking :-(

		if (updated and updated < feeds_updated) or guid in processed:
			continue

		# See above about lying feeds
		#if updated == None or config.getboolean('main','always_store_guid'):

		processed.add(guid) # Remember that we've processed this one

		# Convert from HTML to BBCode which Friendika understands
		# Title is also processed to get rid of HTML entities
		for key in ['title', 'summary']:
			try:
				entry[key] = makebbcode('<html>%s</html>'%entry[key])
			except KeyError:
				pass
		try:
			for i, content in enumerate(entry.content):
				content.value = makebbcode('<html>%s</html>'%content.value)
		except AttributeError:
			pass

		# TODO: Also check link rel="icon" etc.
		try:
			favicon = '://'.join(urlparse.urlparse(entry['link'])[0:2])+'/favicon.ico'
		except KeyError:
			favicon = ''

		try:
			linked_title = '[url=%s][img=16x16]%s[/img]%s[/url]'%(entry['link'],favicon, entry['title'])
		except KeyError:
			linked_title = entry['title']

		message = mako.Template(filename=template_path).render_unicode(entry=entry, favicon=favicon, linked_title=linked_title).encode('utf-8')
		tweet(server, message)

config.set('main','updated',str(time.time()))

with open(conf_path, 'w') as configfile:
    config.write(configfile)

with open(guids_path, 'w') as guids_file:
	pickle.dump(processed, guids_file)
