import time
import telepot
from config import *
import facebook
import requests
from BTrees.OOBTree import OOBTree
from ZODB import FileStorage, DB
import transaction
from persistent import Persistent

storage = FileStorage.FileStorage("memr.fs")
db = DB(storage)
conn = db.open()
dbroot = conn.root()

if "pages" not in dbroot:
    print "pages not in dbroot"
    dbroot["pages"] = OOBTree()

if "aliases" not in dbroot:
    print "aliases not in dbroot"
    dbroot["aliases"] = OOBTree()

pages = dbroot["pages"]
aliases = dbroot["aliases"]
transaction.commit()


class Page(Persistent):

    def __init__(self, id, name):
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

def processPages():
    pagesToRemove = []
    for pageId in pages:
        page = pages[pageId]

        # If nobody follows the page, continue (no point in processing it) and set for removal
        if len(page.users) == 0:
            pagesToRemove.append(pageId)
            continue

        pagePosts = graph.get_connections(page.id, "posts")
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
                        postObj = graph.get_object(postId, **args)
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
        del pages[pageId]
        transaction.commit()

def command(user, cmd, args):
    if cmd == "add" and len(args) >= 1:
        url = args[0]

        if "/" in url:
            slashPos = url.rfind("/", 0, -2)
            url = url[slashPos + 1:]
            if url[-1] == "/":
                url = url[:-1]
        if user not in aliases:
            aliases[user] = {}

        try:
            page = graph.get_object(id=url)
            # if no alias is given, use the page name
            if len(args) == 1:
                name = page["name"]
            else:
                name = " ".join(args[1:])
            id = page["id"]
            if id in pages:
                if pages[id].hasUser(user):
                    bot.sendMessage(user, "You are already subscribed to " + page["name"])
                else:
                    pages[id].addUser(user)
                    aliases[user][name] = id
                    bot.sendMessage(user, "Successfully subscribed to " + page["name"])
                    transaction.commit()
            else:
                pages[id] = Page(id, page["name"])
                pages[id].addUser(user)
                aliases[user][name] = id
                bot.sendMessage(user, "Successfully subscribed to " + page["name"])
                transaction.commit()

        except facebook.GraphAPIError:
            bot.sendMessage(user, "Page does not exist")

    elif cmd == "list":
        if user not in aliases:
            aliases[user] = {}

        output = ""  # list of aliases
        for alias in aliases[user]:
            pageId = aliases[user][alias]
            page = pages[pageId]
            output += alias + " - " + page.name + " - http://www.facebook.com/" + page.id + "/\n"
        if output == "":
            bot.sendMessage(user, "You are not subscribed to any pages")
        else:
            bot.sendMessage(user, output)

    elif cmd == "remove" and len(args) >= 1:
        if user not in aliases:
            aliases[user] = {}
        name = " ".join(args)
        if name in aliases[user]:
            pageId = aliases[user][name]
            page = pages[pageId]
            if page.hasUser(user):
                page.removeUser(user)

                bot.sendMessage(user, "Successfully unsubscribed from page")
                del aliases[user][name]
                transaction.commit()
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
bot = telepot.Bot(key)

accesstoken = facebook.get_app_access_token(fbid, fbsecret)
graph = facebook.GraphAPI(access_token=accesstoken)

# Tell the bot to call handle() when a message is received
bot.notifyOnMessage(handle)
print "Running..."

# This keeps the program running. Idk what the significance of the 10 is, just based on example docs
while 1:
    time.sleep(60)  # maybe change
    processPages()