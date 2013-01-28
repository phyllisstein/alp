from ctypes import *
from ctypes import util
from core import *

cf = cdll.LoadLibrary(util.find_library("CoreFoundation"))
security = cdll.LoadLibrary(util.find_library("Security"))
cs = cdll.LoadLibrary(util.find_library("CoreServices"))


class Keychain:
    def __init__(self, service=None):
        if service:
            self.service = service
        else:
            self.service = bundle()
        self.serviceLen = len(self.service)

    def storePassword(self, account, password):
        acctLen = len(account)
        pwLen = len(password)
        status = security.SecKeychainAddGenericPassword(
                    None,
                    self.serviceLen,
                    self.service,
                    acctLen,
                    account,
                    pwLen,
                    password,
                    None
            )
        return status

    def retrievePassword(self, account):
        acctLen = len(account)
        pwLen = c_uint()
        pwData = c_char_p()

        security.SecKeychainFindGenericPassword(
                    None,
                    self.serviceLen,
                    self.service,
                    acctLen,
                    account,
                    byref(pwLen),
                    byref(pwData),
                    None
            )

        return pwData.value

    def modifyPassword(self, account, newPassword):
        acctLen = len(account)
        newPwLen = len(newPassword)
        itemRef = c_void_p()
        pwLen = c_uint()
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
                    byref(newPwData)
            )
            return modStatus
        else:
            return None
