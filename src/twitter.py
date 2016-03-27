# MFCD/src/twitter.py
# THIS IS WORK IN PROGRESS

from __future__ import absolute_import

import twitter
from config import *
from BTrees.OOBTree import OOBTree
from ZODB import FileStorage, DB
import transaction
from persistent import Persistent
import requests


class Twitter:

	def __init__(self, dbroot):
		self.api = twitter.Api(consumer_key = twitterConsumerKey,
								consumer_secret = twitterConsumerSecret,
								access_token_key = twitterAccessKey,
								access_token_secret = twitterAccessSecret)
		self.graph = None
		if "twitterpages" not in dbroot:
			print "pages not in dbroot"
			dbroot["twitterpages"] = OOBTree()

		self.pages = dbroot["twitterpages"]
		transaction.commit()

	def addSource(self, user, url):
		url = url[1:]

		try:
			page = self.api.GetUser(screen_name=url)
			
			id = page.id
			if id in self.pages:
				if self.pages[id].hasUser(user):
					return (-1, page.name, id)

				else:
					self.pages[id].addUser(user)
					return (1, page.name, id)

			else:
				self.pages[id] = Page(id, page.name, page.screen_name, self.api)
				self.pages[id].addUser(user)
				transaction.commit()
				return (1, page.name, id)

		except twitter.TwitterError as e:
			print e
			return 0;

	def isURLValid(self, url):
		return url[0] == "@"

	def getAlias(self, url):
		url = url[1:]

		try:
			page = self.api.GetUser(screen_name=url)
			
			return page.name

		except twitter.TwitterError:
			print "OOPSIE"
			return 0;

	def getName(self, id):
		# Actively get page name (changes if page changes)

		try:
			page = self.api.GetUser(user_id=id)
			
			return page.name

		except twitter.TwitterError:
			return "N/A";

		# Faster option, but not dynamic, get name from saved names
		# if id in self.pages:
		# 	page = self.pages[id]
		# 	return page.name

	def removeUser(self, user, id):
		if id in self.pages:
			page = self.pages[id]
			if page.hasUser(user):
				page.removeUser(user)
				return True
		return False


	def getURL(self, id):
		if id in self.pages:
			page = self.pages[id]
			return "http://www.twitter.com/" + page.url
		return "ERROR"

	def processPages(self, bot):
		return
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


class Page(Persistent):

	def __init__(self, id, name, url, api):
		self.id = id
		self.url = url
		self.users = []
		self.posts = []
		self.name = name

		# Process existing posts
		pagePosts = api.GetUserTimeline(user_id = id, count = 100)
		for post in pagePosts:
			postId = post.id
			self.posts.append(postId)

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