# MFCD/mfcd.py

from __future__ import absolute_import

import time
import sys
import telepot
from config import *
from src.facebook import Facebook
from src.twitter import Twitter
import requests
from BTrees.OOBTree import OOBTree
from ZODB import FileStorage, DB
import transaction
from persistent import Persistent
import os
from telepot.loop import MessageLoop



storage = FileStorage.FileStorage("mfcd.fs")
db = DB(storage)
conn = db.open()
dbroot = conn.root()

# A list of content sources to test against when a user /adds a page.
# They are listed in order of priority, the first source will be checked first.
contentSources = {"facebook" : Facebook(dbroot)}

if "aliases" not in dbroot:
	print "aliases not in dbroot"
	dbroot["aliases"] = OOBTree()
	transaction.commit()
aliases = dbroot["aliases"]

# Called every X seconds, dispatches a process to each content source
# to send update messages to the user.
def processPages():
	for name in contentSources:
		source = contentSources[name]
		source.processPages(bot)


def command(user, cmd, args):
	# doesn't work, needs fixing
	# if cmd == "kill" and user == admin:
	#	 print "Exiting..."
	#	 os.system('kill %d' % os.getpid())
	#	 print "DID NOT EXIT BAD"

	if cmd == "add" and len(args) >= 1:
		url = args[0]

		s = None
		n = ""

		# Loop through all content sources to see if the link matches
		# the source. (IE @username matches Twitter)
		for name in contentSources:
			source = contentSources[name]
			if source.isURLValid(url):
				s = source
				n = name
				break

		# If it doesn't match the source (Currently, FB accepts any link but
		# will throw an error response further down the line)
		if s == None:
			bot.sendMessage(user, "Invalid URL")
		else:

			# if no alias is given, use the page name
			if len(args) == 1:
				# Get a default alias from the content provider. On Facebook, this is
				# the page name
				name = s.getAlias(url)
			else:
				name = " ".join(args[1:])

			if user not in aliases:
				aliases[user] = {}

			if name in aliases[user]:
				bot.sendMessage(user, "That alias is already in use")
			else:
				print "Trying to add source..."
				# Add the source for that user. Responses are:
				# 0 - if the page doesn't exist
				# (-1, "page name", "id") - if the user is already subscribed
				# (1, "page name", "id") - if the subscription was a success
				result = s.addSource(user, url)
				print result
				# Return if page doesn't exist
				if result == 0:
					bot.sendMessage(user, "Page does not exist")

				# Returned if already subscribed
				elif result[0] == -1:
					bot.sendMessage(user, "You are already subscribed to " + result[1])

				# Returned if success
				elif result[0] == 1:
					bot.sendMessage(user, "Successfully subscribed to " + result[1])

					# Aliases are now handled using a two-part system. n here is
					# the source name, ie "facebook". result[2] is a unique identifier
					# that the source handles. Ie, a Facebook page ID or a Twitter handle
					aliases[user][name] = (n, result[2])
					aliases._p_changed = True
					transaction.commit()

				else:
					# A source returned something invalid in addSource()
					bot.sendMessage(user, "ERROR!")

	elif cmd == "list":
		if user not in aliases:
			aliases[user] = {}

		output = ""  # list of aliases
		for alias in aliases[user]:
			# Tuple, first object is source name, second unique ID
			pageId = aliases[user][alias] 
			# Get the content source for this alias
			source = contentSources[pageId[0]]
			output += str(alias) + " - " + source.getName(pageId[1]) + " - " + source.getURL(pageId[1]) + "/\n"

		if output == "":
			bot.sendMessage(user, "You are not subscribed to any pages")
		else:
			bot.sendMessage(user, output)

	elif cmd == "remove" and len(args) >= 1:
		if user not in aliases:
			aliases[user] = {}
		name = " ".join(args)
		if name in aliases[user]:
			# Tuple, first object is source name, second unique ID
			pageId = aliases[user][name]
			# Get the content source for this alias
			source = contentSources[pageId[0]]

			# Dispatch the removal operation to the content source
			if source.removeUser(user, pageId[1]):
				bot.sendMessage(user, "Successfully unsubscribed from page")
				aliases._p_changed = True
				del aliases[user][name]
				transaction.commit()

			else:
				bot.sendMessage(user, "Could not unsubscribe from page")

		else:
			bot.sendMessage(user, "Alias does not exist, use /list to see aliases")

	elif cmd == "help":
		helpMessage = "List of commands and uses\n\n" \
		+ "add usage:\n" \
		+ "/add <facebook page url> <alias> (optional)\n" \
		+ "The alias is used to unsubscribe from the page, if no alias is given is uses the page name\n\n" \
		+ "remove usage:\n" \
		+ "/remove <alias>\n" \
		+ "Unsubscribes from the page as defined by the alias\n\n" \
		+ "list usage:\n" \
		+ "/list\n" \
		+ "Displays the list of aliases and their respective facebook page"
		bot.sendMessage(user, helpMessage)


# Handle all messages
def handle(msg):
	if "text" in msg:
		text = msg["text"]
		if text[0] == "/":
			user = msg["from"]
			split = text.strip().split(" ")
			cmd = split[0][1:]
			args = split[1:]
			command(user["id"], cmd, args)

# Create our bot instance with our token, passed as a system argument
bot = telepot.Bot(telegramKey)

# Tell the bot to call handle() when a message is received
MessageLoop(bot, handle).run_as_thread()
print "Running..."

# This keeps the program running. Idk what the significance of the 10 is, just based on example docs
while 1:
	time.sleep(10)  # maybe change
	processPages()
