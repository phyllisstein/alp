import subprocess
import os
import plistlib
import json
from xml.etree import ElementTree as ET
from copy import copy
import bs4
import requests
import requests_cache


bundleID = None


def volatile(join=None):
    global bundleID
    if bundleID:
        vPath = os.path.expanduser(os.path.join("~/Library/Caches/com.runningwithcrayons.Alfred-2/Workflow Data/", bundleID))
    else:
        infoPath = os.path.realpath("./info.plist")
        if os.path.exists(infoPath):
            info = plistlib.readPlist(infoPath)
            bundle = info["bundleid"]
            bundleID = bundle

            vPath = os.path.expanduser(os.path.join("~/Library/Caches/com.runningwithcrayons.Alfred-2/Workflow Data/", bundleID))
        else:
            raise Exception("Bundle ID not defined or readable from plist.")

    if not os.path.exists(vPath):
        os.makedirs(vPath)

    if join:
        vPath = os.path.join(vPath, join)

    return vPath


def nonvolatile(join=None):
    global bundleID
    if bundleID:
        nvPath = os.path.expanduser(os.path.join("~/Library/Application Support/Alfred 2/Workflow Data/", bundleID))
    else:
        infoPath = os.path.realpath("./info.plist")
        if os.path.exists(infoPath):
            info = plistlib.readPlist(infoPath)
            bundle = info["bundleid"]
            bundleID = bundle

            nvPath = os.path.expanduser(os.path.join("~/Library/Application Support/Alfred 2/Workflow Data/", bundleID))
        else:
            raise Exception("Bundle ID not defined or readable from plist.")

    if not os.path.exists(nvPath):
        os.makedirs(nvPath)

    if join:
        nvPath = os.path.join(nvPath, join)

    return nvPath


def bundle(newID=None):
    global bundleID
    if newID:
        bundleID = newID

    if not bundleID:
        infoPath = os.path.realpath("./info.plist")
        if os.path.exists(infoPath):
            info = plistlib.readPlist(infoPath)
            bundle = info["bundleid"]
            bundleID = bundle
        else:
            raise Exception("Bundle ID not defined or readable from plist.")

    return bundleID


def find(query):
    output = subprocess.check_output(["mdfind", query])
    returnList = output.split("\n")
    return returnList


class Feedback:
    def __init__(self):
        global bundleID
        if not bundleID:
            infoPath = os.path.realpath("./info.plist")
            if os.path.exists(infoPath):
                info = plistlib.readPlist(infoPath)
                bundle = info["bundleid"]
                bundleID = bundle
            else:
                raise Exception("Bundle ID not defined or readable from plist.")

        self.myResult = ET.Element("items")
        self.defaultData = {
            "title": "Item",
            "subtitle": bundleID,
            "icon": "icon.png"
        }
        self.defaultArgs = {
            "uid": bundleID + ".default",
            "arg": "",
            "valid": "no",
            "autocomplete": bundleID
        }

    def addValidItem(self, uid, arg, dataDict):
        itemToAdd = ET.SubElement(self.myResult, "item")

        args = {"uid": uid, "arg": arg, "valid": "yes", "autocomplete": ""}
        for (k, v) in args.iteritems():
            itemToAdd.set(k, v)

        data = copy(self.defaultData)
        data.update(dataDict)

        for (k, v) in data.iteritems():
            child = ET.SubElement(itemToAdd, k)
            child.text = v

    def addInvalidItem(self, uid, autocomplete, dataDict):
        itemToAdd = ET.SubElement(self.myResult, "item")

        args = {"uid": uid, "arg": "", "valid": "no", "autocomplete": autocomplete}
        for (k, v) in args.iteritems():
            itemToAdd.set(k, v)

        data = copy(self.defaultData)
        data.update(dataDict)

        for (k, v) in data.iteritems():
            child = ET.SubElement(itemToAdd, k)
            child.text = v

    def addItem(self, argsDict, dataDict):
        itemToAdd = ET.SubElement(self.myResult, "item")

        args = copy(self.defaultArgs)
        args.update(argsDict)
        for (k, v) in args.iteritems():
            itemToAdd.set(k, v)

        data = copy(self.defaultData)
        data.update(dataDict)
        for (k, v) in data.iteritems():
            child = ET.SubElement(itemToAdd, k)
            child.text = v

    def __repr__(self):
        return ET.tostring(self.myResult)


class Scraper:
    def __init__(self, url, payload=None, post=False):
        requests_cache.configure("alpy_requests_cache")
        if payload:
            self.request = requests.get(url, params=payload) if not post else requests.post(url, data=payload)
        else:
            self.request = requests.get(url)


class Settings:
    def __init__(self):
        self._settingsPath = nonvolatile("alpy_settings.json")
        if not os.path.exists(self._settingsPath):
            blank = {}
            with open(self._settingsPath, "w") as f:
                json.dump(blank, f)
            self._loadedSettings = blank
        else:
            with open(self._settingsPath, "r") as f:
                payload = json.load(f)
            self._loadedSettings = payload

    def set(self, **kwargs):
        for (k, v) in kwargs.iteritems():
            self._loadedSettings[k] = v
        with open(self._settingsPath, "w") as f:
            json.dump(self._loadedSettings, f)

    def get(self, key, default=None):
        try:
            return self._loadedSettings[key]
        except KeyError:
            return default
