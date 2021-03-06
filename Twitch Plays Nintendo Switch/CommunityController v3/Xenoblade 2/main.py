#!/usr/bin/python3
#   ____                                      _ _          ____            _             _ _           
#  / ___|___  _ __ ___  _ __ ___  _   _ _ __ (_) |_ _   _ / ___|___  _ __ | |_ _ __ ___ | | | ___ _ __ 
# | |   / _ \| '_ ` _ \| '_ ` _ \| | | | '_ \| | __| | | | |   / _ \| '_ \| __| '__/ _ \| | |/ _ \ '__|
# | |__| (_) | | | | | | | | | | | |_| | | | | | |_| |_| | |__| (_) | | | | |_| | | (_) | | |  __/ |   
#  \____\___/|_| |_| |_|_| |_| |_|\__,_|_| |_|_|\__|\__, |\____\___/|_| |_|\__|_|  \___/|_|_|\___|_|   
#                                                   |___/ 
#Copyright (c) 2018 CommunityController
#All rights reserved.
#
#This work is licensed under the terms of the MIT license.
#For a copy, see <https://opensource.org/licenses/MIT>.

import os
import re
import json
import socket
import asyncore
import requests
from threading import Thread
from time import sleep, time

from lib.switch_controller import *

bannedConfig = None
cmmndsConfig = None
serialConfig = None
twitchConfig = None
ccsapiConfig = None

botClient  = None
mainClient = None

commandQueue = []

SERIAL_DEVICE = "COM5"
SERIAL_BAUD = 9600

#Could be useful if we add more ways of inputting commands (Facebook Live, Discord...)
class UserMessage:
	message = ""
	username = ""
	origin = ""
	mod = False
	sub = False

	def loadMessageFromTwitch(self, twitchData: str):
		if "PRIVMSG" in twitchData:
			self.origin = "Twitch"
			if twitchData.find("mod=") != -1:
				self.mod = bool(int(twitchData[twitchData.find("mod=")+4]))
			if twitchData.find("subscriber=") != -1:
				self.sub = bool(int(twitchData[twitchData.find("subscriber=")+11]))
			r = re.compile(r"^:([\w\W]{0,}?)![\w\W]{0,}?@[\w\W]{0,}?\.tmi\.twitch\.tv\s([A-Z]{0,}?)\s#([\w\W]{0,}?)\s:([\w\W]{0,}?)$")
			matches = r.match(twitchData)
			if matches:
				self.username = matches.groups()[0]
				self.message =  matches.groups()[3]


def loadConfig() -> None:
	global twitchConfig
	global serialConfig
	global cmmndsConfig
	global bannedConfig
	global ccsapiConfig

	global commandQueue

	exceptionCount = 0

	os.makedirs("config", exist_ok=True)
	#Loading Twitch config
	try:
		twitchConfig = json.load(open("config/twitch.json", "r"))
		if not all(k in twitchConfig for k in ("host", "port", "mainUsername", "mainPassword")):
			raise
	except:
		twitchConfig = {"host": "irc.chat.twitch.tv", "port": 6667, "mainUsername": "CommunityController", "mainPassword": "XXXXXXXXXX"}
		json.dump(twitchConfig, open("config/twitch.json", "w"))
		exceptionCount += 1
		print("Twitch config file not found! Sample config created.")
	#Loading Serial config
	try:
		serialConfig = json.load(open("config/serial.json", "r"))
		if not all(k in serialConfig for k in ("device", "baud")):
			raise
	except:
		serialConfig = {"device": "COM5", "baud": 9600}
		json.dump(serialConfig, open("config/serial.json", "w"))
		exceptionCount += 1
		print("Serial config file not found! Sample config created.")
	#Loading Commands config
	try:
		cmmndsConfig = json.load(open("config/commands.json", "r"))
	except:
		cmmndsConfig = {"A": "controller.push_button(BUTTON_A)"}
		json.dump(cmmndsConfig, open("config/commands.json", "w"))
		exceptionCount += 1
		print("Commands config file not found! Sample config created.")
	#Loading Community Controller site API and shadowban config
	try:
		ccsapiConfig = json.load(open("config/CommunityControllerAPI.json", "r"))
		r = requests.get(ccsapiConfig["url"] + "/shadowbans", headers={"Accept": "application/json", "Authorization": "Bearer " + ccsapiConfig["token"]})
		bannedConfig = r.json()
		json.dump(bannedConfig, open("config/shadowbans.json", "w"))
	except:
		ccsapiConfig = {"url": "https://communitycontroller.com/api", "token": "XXXXXXXXXX"}
		json.dump(ccsapiConfig, open("config/CommunityControllerAPI.json", "w"))
		try:
			bannedConfig = json.load(open("config/shadowbans.json", "r"))
		except:
			bannedConfig = {"shadowbans": []}
			json.dump(bannedConfig, open("config/shadowbans.json", "w"))

	try:
		commandQueueJson = json.load(open("config/queue.json", "r"))
		commandQueue = commandQueueJson["queue"]
	except:
		commandQueue = []
		commandQueueJson = {"queue": []}
		json.dump(commandQueueJson, open("config/queue.json", "w"))

	if exceptionCount >= 1:
		print("Please edit the config files and try again.")
		exit(0)

#Copy/Pasted it from V1. Might rewrite it if needed.
def customCommand(single: str) -> None:
	command_executed = False
	tmpr = single[7:single.find(")")].strip().replace("_", " ")  # tmpr == "smthg"

	combine = []

	if tmpr[0:1] == "[" and tmpr.find("]") > 0:  # tmpr == "a[b, ...]c"
		combine = tmpr[tmpr.find("[") + 1:tmpr.find("]")].split(";")  # combine == ["b", "..."]

		tmpr = tmpr[tmpr.find("]") + 1:]  # tmpr == "c"
	elif tmpr.find(";") > -1:  # tmpr == "x,y"
		combine = [tmpr[0:tmpr.find(";")]]  # combine == ["x"]
	else:  # tmpr = "x"
		combine = [tmpr]  # combine == ["x"]

		tmpr = ""

	tmpr = tmpr[tmpr.find(";") + 1:].strip()

	# At this point...
	# combine is an array of commands
	# tmpr is a string supposedly containing the duration of the custom command

	duration = 0.02
	try:
		duration = float(tmpr)

		if duration > 0 and duration <= 1:  # the duration has to be between 0 and 1 second
			duration = duration
		else:
			duration = 0.02

	except:
		0

	cmd = []  # array of the commands to execute, again...

	for i in combine:
		i = i.strip().replace(" ", "_")

		if i in ["PLUS", "START"]:
			cmd.append(BUTTON_PLUS)
		elif i in ["MINUS", "SELECT"]:
			cmd.append(BUTTON_MINUS)

		elif i == "A":
			cmd.append(BUTTON_A)
		elif i == "B":
			cmd.append(BUTTON_B)
		elif i == "X":
			cmd.append(BUTTON_X)
		elif i == "Y":
			cmd.append(BUTTON_Y)

		elif i in ["UP", "DUP", "D_UP"]:
			cmd.append(DPAD_UP)
		elif i in ["DOWN", "DDOWN", "D_DOWN"]:
			cmd.append(DPAD_DOWN)
		elif i in ["LEFT", "DLEFT", "D_LEFT"]:
			cmd.append(DPAD_LEFT)
		elif i in ["RIGHT", "DRIGHT", "D_RIGHT"]:
			cmd.append(DPAD_RIGHT)

		elif i in ["L", "LB"]:
			cmd.append(BUTTON_L)
		elif i in ["R", "RB"]:
			cmd.append(BUTTON_R)
		elif i in ["ZL", "LT"]:
			cmd.append(BUTTON_ZL)
		elif i in ["ZR", "RT"]:
			cmd.append(BUTTON_ZR)

		elif i in ["LCLICK", "L3"]:
			cmd.append(BUTTON_LCLICK)
		elif i in ["RCLICK", "R3"]:
			cmd.append(BUTTON_RCLICK)

		elif i in ["LUP", "L_UP"]:
			cmd.append("L_UP")
		elif i in ["LDOWN", "L_DOWN"]:
			cmd.append("L_DOWN")
		elif i in ["LLEFT", "L_LEFT"]:
			cmd.append("L_LEFT")
		elif i in ["LRIGHT", "L_RIGHT"]:
			cmd.append("L_RIGHT")
		elif i in ["RUP", "R_UP"]:
			cmd.append("R_UP")
		elif i in ["RDOWN", "R_DOWN"]:
			cmd.append("R_DOWN")
		elif i in ["RLEFT", "R_LEFT"]:
			cmd.append("R_LEFT")
		elif i in ["RRIGHT", "R_RIGHT"]:
			cmd.append("R_RIGHT")

		elif i == "WAIT":
			cmd.append("WAIT")

	for i in cmd:  # buttons to hold
		if i in [BUTTON_PLUS, BUTTON_MINUS, BUTTON_A, BUTTON_B, BUTTON_X, BUTTON_Y, BUTTON_L, BUTTON_R,
				 BUTTON_ZL, BUTTON_ZR, BUTTON_LCLICK, BUTTON_RCLICK]:
			controller.hold_buttons(i)
			command_executed = True
		elif i in [DPAD_UP, DPAD_DOWN, DPAD_LEFT, DPAD_RIGHT]:
			controller.hold_dpad(i)
			command_executed = True
		elif i == "L_UP":
			controller.move_forward(MODE_BACK_VIEW)
			command_executed = True
		elif i == "L_DOWN":
			controller.move_backward(MODE_BACK_VIEW)
			command_executed = True
		elif i == "L_LEFT":
			controller.move_left()
			command_executed = True
		elif i == "L_RIGHT":
			controller.move_right()
			command_executed = True
		elif i == "R_UP":
			controller.look_up()
			command_executed = True
		elif i == "R_DOWN":
			controller.look_down()
			command_executed = True
		elif i == "R_LEFT":
			controller.look_left()
			command_executed = True
		elif i == "R_RIGHT":
			controller.look_right()
			command_executed = True
		elif i == "WAIT":
			command_executed = True

	if command_executed:  # sleep if any command has been executed
		sleep(duration)

	for i in cmd:  # release the buttons
		if i in [BUTTON_PLUS, BUTTON_MINUS, BUTTON_A, BUTTON_B, BUTTON_X, BUTTON_Y, BUTTON_L, BUTTON_R,
				 BUTTON_ZL, BUTTON_ZR, BUTTON_LCLICK, BUTTON_RCLICK]:
			controller.release_buttons(i)
		elif i in [DPAD_UP, DPAD_DOWN, DPAD_LEFT, DPAD_RIGHT]:
			controller.release_dpad()
		elif i in ["L_UP", "L_DOWN", "L_LEFT", "L_RIGHT"]:
			controller.release_left_stick()
		elif i in ["R_UP", "R_DOWN", "R_LEFT", "R_RIGHT"]:
			controller.release_right_stick()

def isUserBanned(username: str):
	global bannedConfig
	isBanned = False
	for u in bannedConfig["shadowbans"]:
		if u["user"] == username:
			isBanned = True
	return isBanned

def executeCommand(command: str):
	global cmmndsConfig
	print("executeCommand(" + command + ")")
	if command in cmmndsConfig:
		exec(cmmndsConfig[command])
		sleep(0.1)

def useCommand(command: str):
	#Anarchy mode
	if command[0:7] == "CUSTOM(" and command.find(")") > 7:
		print("Using a custom command!")
		customCommand(command)
	else:
		simultaneousCommands = command.split("_&_")
		if len(simultaneousCommands) > 1:
			threadsArr = []
			for cmd in simultaneousCommands:
				threadsArr.append(Thread(target=executeCommand, args=[cmd]))
				threadsArr[-1].start()
			for t in threadsArr:
				t.join()
		else:
			executeCommand(command)

def addToQueue(command: str):
	global commandQueue
	commandQueue.append(command)
	commandQueueJson = {"queue": commandQueue}
	json.dump(commandQueueJson, open("config/queue.json", "w"))

def commandQueueThread():
	global commandQueue
	while True:
		if len(commandQueue) > 0:
			useCommand(commandQueue[0])
			commandQueue.pop(0)
			commandQueueJson = {"queue": commandQueue}
			json.dump(commandQueueJson, open("config/queue.json", "w"))

def parseMessage(userMessage):
	message = userMessage.message.strip().upper()
	if len(message) > 0:
		if message[-1] == ",": #Removes the comma at the end of the message if there's one
			message = message[:-1]
	splitMessage = message.split(",")
	
	maxCommands = 8
	if userMessage.sub:
		maxCommands = 8
	if userMessage.mod:
		maxCommands = 10

	print(userMessage.username + " (from " + userMessage.origin + "): " + userMessage.message)
	
	if len(splitMessage) <= maxCommands and not isUserBanned(userMessage.username):
		for single in splitMessage:
			single = single.strip().replace(" ", "_")
			addToQueue(single)


class TwitchIRC(asyncore.dispatcher):
	username = None
	password = None
	channel = None
	authenticated = False

	def __init__(self, username: str, password: str, channel: str) -> None:
		assert username is not None, "No username specified!"
		assert password is not None, "No password specified!"
		assert channel  is not None, "No channel specified!"

		global twitchConfig

		self.username = username
		self.password = password
		self.channel = channel

		asyncore.dispatcher.__init__(self)
		self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
		self.connect((twitchConfig["host"], twitchConfig["port"]))
		self.buffer = bytes("PASS %s\r\nNICK %s\r\n" % (password, username), "utf8")

	def handle_connect(self):
		pass

	def handle_close(self):
		self.close()

	def handle_read(self):
			data = self.recv(2048).decode("utf8", errors="ignore").rstrip()
			if "Welcome, GLHF!" in data and not self.authenticated:
				self.authenticated = True
				self.buffer += bytes("JOIN #%s\r\n" % (self.channel), "utf8")
				print("Successfully authenticated!")
				print("JOIN #%s\r\n" % (self.channel))
				#self.buffer += bytes("CAP REQ :twitch.tv/tags\r\n", "utf8")
			elif data == "PING :tmi.twitch.tv":
				print("Ping!")
				self.buffer += b"PONG :tmi.twitch.tv\r\n"
				print("Pong!")
			elif "%s.tmi.twitch.tv" % (self.channel) not in data or self.username in data:  #chat messages here
				if "PRIVMSG" in data:
					message = UserMessage()
					message.loadMessageFromTwitch(data)
					Thread(target=parseMessage, args=[message]).start()
	
	def readable(self):
		return True
	
	def writable(self):
		return (len(self.buffer) > 0)

	def handle_write(self):
		sent = self.send(self.buffer)
		self.buffer = self.buffer[sent:]


if __name__ == "__main__":
	loadConfig()
	with Controller() as controller:
		try:
			mainClient = TwitchIRC(twitchConfig["mainUsername"], twitchConfig["mainPassword"], twitchConfig["mainUsername"].lower())
			Thread(target=commandQueueThread).start()
		except KeyboardInterrupt:
			controller.reset.wait()
			exit(0)
		asyncore.loop()

#くコ:彡