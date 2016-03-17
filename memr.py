import sys
import time
import telepot
from config import *

# Handle all messages
def handle(msg):
    print msg["text"]


# Create our bot instance with our token, passed as a system argument
bot = telepot.Bot(key)

# Tell the bot to call handle() when a message is received
bot.notifyOnMessage(handle)
print "Running..."

# This keeps the program running. Idk what the significance of the 10 is, just based on example docs
while 1:
    time.sleep(10)