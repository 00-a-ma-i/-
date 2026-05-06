dictionary = {
    1 : 'one',
    2 : 'two'
}
print(dictionary.pop(4, None))
print(dictionary.get(3))

import mimetypes
filename = 'file.jpg'
print(mimetypes.guess_type(filename))
mime_type, _ = mimetypes.guess_type(filename)
print(mime_type, type(mime_type))
string = '1234'
print(string.startswith('1'))

class test() :
    def __init__(self) :
        self.one = 1

test1 = test()

import os
print(os.path.join('1', '2', '3'))