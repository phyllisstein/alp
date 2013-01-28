from ctypes import *
from ctypes import util
from core import *

security = cdll.LoadLibrary(util.find_library("Security"))


class Keychain:
    def __init__(self, service=None):
        if service:
            self.service = c_char_p(service)
            self.serviceLen = c_ulong(len(service))
        else:
            self.service = c_char_p(bundle())
            self.serviceLen = c_ulong(len(bundle()))

    def storePassword(self, account, password):
        acctLen = c_ulong(len(account))
        pwLen = c_ulong(len(password))
        acctData = c_char_p(account)
        pwData = c_char_p(password)
        status = security.SecKeychainAddGenericPassword(
                    None,
                    self.serviceLen,
                    self.service,
                    acctLen,
                    acctData,
                    pwLen,
                    pwData,
                    None
            )
        return status

    def retrievePassword(self, account):
        acctLen = c_ulong(len(account))
        acctData = c_char_p(account)
        pwLen = c_ulong()
        pwData = c_char_p()

        security.SecKeychainFindGenericPassword(
                    None,
                    self.serviceLen,
                    self.service,
                    acctLen,
                    acctData,
                    byref(pwLen),
                    byref(pwData),
                    None
            )

        return pwData.value

    def modifyPassword(self, account, newPassword):
        acctLen = c_ulong(len(account))
        newPwLen = c_ulong(len(newPassword))
        itemRef = c_void_p()
        pwLen = c_ulong()
        pwData = c_char_p()
        newPwData = c_char_p(newPassword)

        status = security.SecKeychainFindGenericPassword(
                    None,
                    self.serviceLen,
                    self.service,
                    acctLen,
                    account,
                    byref(pwLen),
                    byref(pwData),
                    byref(itemRef)
            )
        if status == 0:
            modStatus = security.SecKeychainItemModifyAttributesAndData(
                    itemRef,
                    None,
                    newPwLen,
                    newPwData
            )
            return modStatus
        else:
            return None
