# MFCD/src/facebook.py

from __future__ import absolute_import

import facebook
from config import *
from BTrees.OOBTree import OOBTree
from ZODB import FileStorage, DB
import transaction
from persistent import Persistent
import requests

# This is an example content source
class Facebook:

	# Init function sets up all needed APIs, loads saved info on page
	# subscriptions for this content source
	def __init__(self, dbroot):
		accessToken = facebook.get_app_access_token(fbid, fbsecret)
		self.graph = facebook.GraphAPI(access_token = accessToken)

		if "fbpages" not in dbroot:
			print "pages not in dbroot"
			dbroot["fbpages"] = OOBTree()

		self.pages = dbroot["fbpages"]
		transaction.commit()

	# Parameters:
	# 	Unique user ID, URL to the page
	# Returns:
	# 	0 - if page doesn't exist
	#	(-1, "page name", "id") - if page already subscribed to
	#	(1, "page name", "id") - if success
	def addSource(self, user, url):

		if "/" in url:
			slashPos = url.rfind("/", 0, -2)
			url = url[slashPos + 1:]
			if url[-1] == "/":
				url = url[:-1]

		try:
			page = self.graph.get_object(id=url)
			
			id = page["id"]
			if id in self.pages:
				if self.pages[id].hasUser(user):
					return (-1, page["name"], id)

				else:
					self.pages[id].addUser(user)
					return (1, page["name"], id)

			else:
				self.pages[id] = Page(id, page["name"], self.graph)
				self.pages[id].addUser(user)
				transaction.commit()
				return (1, page["name"], id)

		except facebook.GraphAPIError:
			return 0;

	# Parameters:
	#	URL to the page
	# Returns:
	#	Boolean, if this URL matches the content source
	#	This does not mean that the URL links to a valid page,
	#	just that it matches the source. @UNUSEDTWITTERHANDLE
	#	should return True even if the handle doesn't exist
	def isURLValid(self, url):
		return True # Temporary, all pages are treated as potential FB pages for now

	# Parameters:
	#	URL to the page
	# Returns:
	#	A default alias for this page
	def getAlias(self, url):
		if "/" in url:
			slashPos = url.rfind("/", 0, -2)
			url = url[slashPos + 1:]
			if url[-1] == "/":
				url = url[:-1]

		try:
			page = self.graph.get_object(id=url)
			
			# Page name is the default alias for FB
			return page["name"]

		except facebook.GraphAPIError:
			return 0;

	# Parameters:
	#	Some form of page ID, the same type returned as the
	#	third tuple element in addSource()
	# Returns:
	#	The name for this page, for display in /list
	def getName(self, id):
		# Actively get page name (changes if page changes)

		try:
			page = self.graph.get_object(id=id)
			
			return page["name"]

		except facebook.GraphAPIError:
			return "N/A";

		# Faster option, but not dynamic, get name from saved names
		# if id in self.pages:
		# 	page = self.pages[id]
		# 	return page.name

	# Parameters:
	#	Unique user id, some form of page ID, the same type
	#	returned as the third tuple element in addSource()
	# Returns:
	#	If the removal worked
	def removeUser(self, user, id):
		if id in self.pages:
			page = self.pages[id]
			if page.hasUser(user):
				page.removeUser(user)
				return True
		return False

	# Parameters:
	#	Some form of page ID, the same type returned as the
	#	third tuple element in addSource()
	# Returns:
	#	A link to this page, for display in /list
	def getURL(self, id):
		return "http://www.facebook.com/" + id

	# Parameters:
	#	The bot instance, so this can send messages.
	#	TODO: Don't require this param, but rather a generic
	#	send message callback.
	def processPages(self, bot):
		pagesToRemove = []
		for pageId in self.pages:
			page = self.pages[pageId]

			# If nobody follows the page, continue (no point in processing it) and set for removal
			if len(page.users) == 0:
				pagesToRemove.append(pageId)
				continue

			pagePosts = self.graph.get_connections(page.id, "posts")
			foundOld = False
			print "Processing page with id " + pageId
			while 1:
				try:
					for post in pagePosts["data"]:
						postId = post["id"]
						if postId in page.posts:
							print "Old post found"
							foundOld = True
							break
						else:
							page.addPost(postId)
							transaction.commit()
							args = {'fields' : 'id,full_picture,message,attachments'}
							postObj = self.graph.get_object(postId, **args)
							if "full_picture" in postObj:
								if "subattachments" in postObj["attachments"]["data"][0]:
									for uid in page.users:
										print "Sending message"
										first = True
										for pic in postObj["attachments"]["data"][0]["subattachments"]["data"]:
											if first:
												first = False
												bot.sendMessage(uid, page.name + "\n" + pic["media"]["image"]["src"])
											else:
												bot.sendMessage(uid, pic["media"]["image"]["src"])

										if "message" in postObj:
											bot.sendMessage(uid, postObj["message"])
								else:
									for uid in page.users:
										print "Sending message"
										bot.sendMessage(uid, page.name + "\n" + postObj["full_picture"])
										if "message" in postObj:
											bot.sendMessage(uid, postObj["message"])

					if foundOld:
						break
					pagePosts = requests.get(pagePosts['paging']['next']).json()
				except KeyError:
					break

		# Remove unfollowed pages
		for pageId in pagesToRemove:
			del self.pages[pageId]
			transaction.commit()

# Page class for internal usage.
class Page(Persistent):

	def __init__(self, id, name, graph):
		self.id = id
		self.users = []
		self.posts = []
		self.name = name

		# Process existing posts
		pagePosts = graph.get_connections(id, "posts")
		while 1:
			try:
				for post in pagePosts["data"]:
					postId = post["id"]
					self.posts.append(postId)
				pagePosts = requests.get(pagePosts['paging']['next']).json()
			except KeyError:
				break

	def addUser(self, uid):
		self.users.append(uid)
		self._p_changed = True

	def hasUser(self, uid):
		return uid in self.users

	def removeUser(self, uid):
		self.users.remove(uid)
		self._p_changed = True

	def addPost(self, post):
		self.posts.append(post)
		self._p_changed = True