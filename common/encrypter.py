#!/usr/bin/python
# --encoding:utf-8--

from Crypto.Cipher import AES
from tornado.options import options


class Crypter():
    def __init__(self, key):
        self.key = key
        self.mode = AES.MODE_CBC
        
    def encrypt(self, text):
        cryptor = AES.new(self.key, self.mode, self.key)
        length = 16
        count = text.count('')
        if count < length:
            add = (length-count) + 1
            text = text + (' ' * add)
        elif count > length:
            add = (length-(count % length)) + 1
            text = text + (' ' * add)
        ciphertext = cryptor.encrypt(text)
        return ciphertext
    
    def decrypt(self, text):
        cryptor = AES.new(self.key, self.mode, self.key)
        plain_text  = cryptor.decrypt(text)
        return plain_text.rstrip()


crypter = Crypter(options.encrypt_key)


if __name__ == "__main__":

        text = "hi python!"
        key = "2222222222222222"
        en = Crypter(key)
        entext = en.encrypt(text)
        print entext

        detext = en.decrypt(entext)
        print detext
