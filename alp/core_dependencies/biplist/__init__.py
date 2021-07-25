"""biplist -- a library for reading and writing binary property list files.

Binary Property List (plist) files provide a faster and smaller serialization
format for property lists on OS X. This is a library for generating binary
plists which can be read by OS X, iOS, or other clients.

The API models the plistlib API, and will call through to plistlib when
XML serialization or deserialization is required.

To generate plists with UID values, wrap the values with the Uid object. The
value must be an int.

To generate plists with NSData/CFData values, wrap the values with the
Data object. The value must be a string.

Date values can only be datetime.datetime objects.

The exceptions InvalidPlistException and NotBinaryPlistException may be 
thrown to indicate that the data cannot be serialized or deserialized as
a binary plist.

Plist generation example:
    
    from biplist import *
    from datetime import datetime
    plist = {'aKey':'aValue',
             '0':1.322,
             'now':datetime.now(),
             'list':[1,2,3],
             'tuple':('a','b','c')
             }
    try:
        writePlist(plist, "example.plist")
    except (InvalidPlistException, NotBinaryPlistException), e:
        print "Something bad happened:", e

Plist parsing example:

    from biplist import *
    try:
        plist = readPlist("example.plist")
        print plist
    except (InvalidPlistException, NotBinaryPlistException), e:
        print "Not a plist:", e
"""

import sys
from collections import namedtuple
import calendar
import datetime
import math
import plistlib
from struct import pack, unpack
import sys
import time

import alp.core_dependencies.six as six

__all__ = [
    'Uid', 'Data', 'readPlist', 'writePlist', 'readPlistFromString',
    'writePlistToString', 'InvalidPlistException', 'NotBinaryPlistException'
]

apple_reference_date_offset = 978307200

class Uid(int):
    """Wrapper around integers for representing UID values. This
       is used in keyed archiving."""
    def __repr__(self):
        return "Uid(%d)" % self

class Data(six.binary_type):
    """Wrapper around str types for representing Data values."""
    pass

class InvalidPlistException(Exception):
    """Raised when the plist is incorrectly formatted."""
    pass

class NotBinaryPlistException(Exception):
    """Raised when a binary plist was expected but not encountered."""
    pass

def readPlist(pathOrFile):
    """Raises NotBinaryPlistException, InvalidPlistException"""
    didOpen = False
    result = None
    if isinstance(pathOrFile, (six.binary_type, six.text_type)):
        pathOrFile = open(pathOrFile, 'rb')
        didOpen = True
    try:
        reader = PlistReader(pathOrFile)
        result = reader.parse()
    except NotBinaryPlistException as e:
        try:
            pathOrFile.seek(0)
            result = plistlib.readPlist(pathOrFile)
            result = wrapDataObject(result, for_binary=True)
        except Exception as e:
            raise InvalidPlistException(e)
    if didOpen:
        pathOrFile.close()
    return result

def wrapDataObject(o, for_binary=False):
    if isinstance(o, Data) and not for_binary:
        o = plistlib.Data(o)
    elif isinstance(o, plistlib.Data) and for_binary:
        o = Data(o.data)
    elif isinstance(o, tuple):
        o = wrapDataObject(list(o), for_binary)
        o = tuple(o)
    elif isinstance(o, list):
        for i in range(len(o)):
            o[i] = wrapDataObject(o[i], for_binary)
    elif isinstance(o, dict):
        for k in o:
            o[k] = wrapDataObject(o[k], for_binary)
    return o

def writePlist(rootObject, pathOrFile, binary=True):
    if not binary:
        rootObject = wrapDataObject(rootObject, binary)
        return plistlib.writePlist(rootObject, pathOrFile)
    else:
        didOpen = False
        if isinstance(pathOrFile, (six.binary_type, six.text_type)):
            pathOrFile = open(pathOrFile, 'wb')
            didOpen = True
        writer = PlistWriter(pathOrFile)
        result = writer.writeRoot(rootObject)
        if didOpen:
            pathOrFile.close()
        return result

def readPlistFromString(data):
    return readPlist(six.BytesIO(data))

def writePlistToString(rootObject, binary=True):
    if not binary:
        rootObject = wrapDataObject(rootObject, binary)
        if six.PY3:
            return plistlib.writePlistToBytes(rootObject)
        else:
            return plistlib.writePlistToString(rootObject)
    else:
        io = six.BytesIO()
        writer = PlistWriter(io)
        writer.writeRoot(rootObject)
        return io.getvalue()

def is_stream_binary_plist(stream):
    stream.seek(0)
    header = stream.read(7)
    if header == six.b('bplist0'):
        return True
    else:
        return False

PlistTrailer = namedtuple('PlistTrailer', 'offsetSize, objectRefSize, offsetCount, topLevelObjectNumber, offsetTableOffset')
PlistByteCounts = namedtuple('PlistByteCounts', 'nullBytes, boolBytes, intBytes, realBytes, dateBytes, dataBytes, stringBytes, uidBytes, arrayBytes, setBytes, dictBytes')

class PlistReader(object):
    file = None
    contents = ''
    offsets = None
    trailer = None
    currentOffset = 0
    
    def __init__(self, fileOrStream):
        """Raises NotBinaryPlistException."""
        self.reset()
        self.file = fileOrStream
    
    def parse(self):
        return self.readRoot()
    
    def reset(self):
        self.trailer = None
        self.contents = ''
        self.offsets = []
        self.currentOffset = 0
    
    def readRoot(self):
        result = None
        self.reset()
        # Get the header, make sure it's a valid file.
        if not is_stream_binary_plist(self.file):
            raise NotBinaryPlistException()
        self.file.seek(0)
        self.contents = self.file.read()
        if len(self.contents) < 32:
            raise InvalidPlistException("File is too short.")
        trailerContents = self.contents[-32:]
        try:
            self.trailer = PlistTrailer._make(unpack("!xxxxxxBBQQQ", trailerContents))
            offset_size = self.trailer.offsetSize * self.trailer.offsetCount
            offset = self.trailer.offsetTableOffset
            offset_contents = self.contents[offset:offset+offset_size]
            offset_i = 0
            while offset_i < self.trailer.offsetCount:
                begin = self.trailer.offsetSize*offset_i
                tmp_contents = offset_contents[begin:begin+self.trailer.offsetSize]
                tmp_sized = self.getSizedInteger(tmp_contents, self.trailer.offsetSize)
                self.offsets.append(tmp_sized)
                offset_i += 1
            self.setCurrentOffsetToObjectNumber(self.trailer.topLevelObjectNumber)
            result = self.readObject()
        except TypeError as e:
            raise InvalidPlistException(e)
        return result
    
    def setCurrentOffsetToObjectNumber(self, objectNumber):
        self.currentOffset = self.offsets[objectNumber]
    
    def readObject(self):
        result = None
        tmp_byte = self.contents[self.currentOffset:self.currentOffset+1]
        marker_byte = unpack("!B", tmp_byte)[0]
        format = (marker_byte >> 4) & 0x0f
        extra = marker_byte & 0x0f
        self.currentOffset += 1
        
        def proc_extra(extra):
            if extra == 0b1111:
                #self.currentOffset += 1
                extra = self.readObject()
            return extra
        
        # bool, null, or fill byte
        if format == 0b0000:
            if extra == 0b0000:
                result = None
            elif extra == 0b1000:
                result = False
            elif extra == 0b1001:
                result = True
            elif extra == 0b1111:
                pass # fill byte
            else:
                raise InvalidPlistException("Invalid object found at offset: %d" % (self.currentOffset - 1))
        # int
        elif format == 0b0001:
            extra = proc_extra(extra)
            result = self.readInteger(pow(2, extra))
        # real
        elif format == 0b0010:
            extra = proc_extra(extra)
            result = self.readReal(extra)
        # date
        elif format == 0b0011 and extra == 0b0011:
            result = self.readDate()
        # data
        elif format == 0b0100:
            extra = proc_extra(extra)
            result = self.readData(extra)
        # ascii string
        elif format == 0b0101:
            extra = proc_extra(extra)
            result = self.readAsciiString(extra)
        # Unicode string
        elif format == 0b0110:
            extra = proc_extra(extra)
            result = self.readUnicode(extra)
        # uid
        elif format == 0b1000:
            result = self.readUid(extra)
        # array
        elif format == 0b1010:
            extra = proc_extra(extra)
            result = self.readArray(extra)
        # set
        elif format == 0b1100:
            extra = proc_extra(extra)
            result = set(self.readArray(extra))
        # dict
        elif format == 0b1101:
            extra = proc_extra(extra)
            result = self.readDict(extra)
        else:    
            raise InvalidPlistException("Invalid object found: {format: %s, extra: %s}" % (bin(format), bin(extra)))
        return result
    
    def readInteger(self, bytes):
        result = 0
        original_offset = self.currentOffset
        data = self.contents[self.currentOffset:self.currentOffset+bytes]
        result = self.getSizedInteger(data, bytes)
        self.currentOffset = original_offset + bytes
        return result
    
    def readReal(self, length):
        result = 0.0
        to_read = pow(2, length)
        data = self.contents[self.currentOffset:self.currentOffset+to_read]
        if length == 2: # 4 bytes
            result = unpack('>f', data)[0]
        elif length == 3: # 8 bytes
            result = unpack('>d', data)[0]
        else:
            raise InvalidPlistException("Unknown real of length %d bytes" % to_read)
        return result
    
    def readRefs(self, count):    
        refs = []
        i = 0
        while i < count:
            fragment = self.contents[self.currentOffset:self.currentOffset+self.trailer.objectRefSize]
            ref = self.getSizedInteger(fragment, len(fragment))
            refs.append(ref)
            self.currentOffset += self.trailer.objectRefSize
            i += 1
        return refs
    
    def readArray(self, count):
        result = []
        values = self.readRefs(count)
        i = 0
        while i < len(values):
            self.setCurrentOffsetToObjectNumber(values[i])
            value = self.readObject()
            result.append(value)
            i += 1
        return result
    
    def readDict(self, count):
        result = {}
        keys = self.readRefs(count)
        values = self.readRefs(count)
        i = 0
        while i < len(keys):
            self.setCurrentOffsetToObjectNumber(keys[i])
            key = self.readObject()
            self.setCurrentOffsetToObjectNumber(values[i])
            value = self.readObject()
            result[key] = value
            i += 1
        return result
    
    def readAsciiString(self, length):
        result = unpack("!%ds" % length, self.contents[self.currentOffset:self.currentOffset+length])[0]
        self.currentOffset += length
        return result
    
    def readUnicode(self, length):
        actual_length = length*2
        data = self.contents[self.currentOffset:self.currentOffset+actual_length]
        # unpack not needed?!! data = unpack(">%ds" % (actual_length), data)[0]
        self.currentOffset += actual_length
        return data.decode('utf_16_be')
    
    def readDate(self):
        global apple_reference_date_offset
        result = unpack(">d", self.contents[self.currentOffset:self.currentOffset+8])[0]
        result = datetime.datetime.utcfromtimestamp(result + apple_reference_date_offset)
        self.currentOffset += 8
        return result
    
    def readData(self, length):
        result = self.contents[self.currentOffset:self.currentOffset+length]
        self.currentOffset += length
        return Data(result)
    
    def readUid(self, length):
        return Uid(self.readInteger(length+1))
    
    def getSizedInteger(self, data, bytes):
        result = 0
        # 1, 2, and 4 byte integers are unsigned
        if bytes == 1:
            result = unpack('>B', data)[0]
        elif bytes == 2:
            result = unpack('>H', data)[0]
        elif bytes == 4:
            result = unpack('>L', data)[0]
        elif bytes == 8:
            result = unpack('>q', data)[0]
        else:
            raise InvalidPlistException("Encountered integer longer than 8 bytes.")
        return result

class HashableWrapper(object):
    def __init__(self, value):
        self.value = value
    def __repr__(self):
        return "<HashableWrapper: %s>" % [self.value]

class BoolWrapper(object):
    def __init__(self, value):
        self.value = value
    def __repr__(self):
        return "<BoolWrapper: %s>" % self.value

class PlistWriter(object):
    header = six.b('bplist00bybiplist1.0')
    file = None
    byteCounts = None
    trailer = None
    computedUniques = None
    writtenReferences = None
    referencePositions = None
    wrappedTrue = None
    wrappedFalse = None
    
    def __init__(self, file):
        self.reset()
        self.file = file
        self.wrappedTrue = BoolWrapper(True)
        self.wrappedFalse = BoolWrapper(False)

    def reset(self):
        self.byteCounts = PlistByteCounts(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.trailer = PlistTrailer(0, 0, 0, 0, 0)
        
        # A set of all the uniques which have been computed.
        self.computedUniques = set()
        # A list of all the uniques which have been written.
        self.writtenReferences = {}
        # A dict of the positions of the written uniques.
        self.referencePositions = {}
        
    def positionOfObjectReference(self, obj):
        """If the given object has been written already, return its
           position in the offset table. Otherwise, return None."""
        return self.writtenReferences.get(obj)
        
    def writeRoot(self, root):
        """
        Strategy is:
        - write header
        - wrap root object so everything is hashable
        - compute size of objects which will be written
          - need to do this in order to know how large the object refs
            will be in the list/dict/set reference lists
        - write objects
          - keep objects in writtenReferences
          - keep positions of object references in referencePositions
          - write object references with the length computed previously
        - computer object reference length
        - write object reference positions
        - write trailer
        """
        output = self.header
        wrapped_root = self.wrapRoot(root)
        should_reference_root = True#not isinstance(wrapped_root, HashableWrapper)
        self.computeOffsets(wrapped_root, asReference=should_reference_root, isRoot=True)
        self.trailer = self.trailer._replace(**{'objectRefSize':self.intSize(len(self.computedUniques))})
        (_, output) = self.writeObjectReference(wrapped_root, output)
        output = self.writeObject(wrapped_root, output, setReferencePosition=True)
        
        # output size at this point is an upper bound on how big the
        # object reference offsets need to be.
        self.trailer = self.trailer._replace(**{
            'offsetSize':self.intSize(len(output)),
            'offsetCount':len(self.computedUniques),
            'offsetTableOffset':len(output),
            'topLevelObjectNumber':0
            })
        
        output = self.writeOffsetTable(output)
        output += pack('!xxxxxxBBQQQ', *self.trailer)
        self.file.write(output)

    def wrapRoot(self, root):
        if isinstance(root, bool):
            if root is True:
                return self.wrappedTrue
            else:
                return self.wrappedFalse
        elif isinstance(root, set):
            n = set()
            for value in root:
                n.add(self.wrapRoot(value))
            return HashableWrapper(n)
        elif isinstance(root, dict):
            n = {}
            for key, value in six.iteritems(root):
                n[self.wrapRoot(key)] = self.wrapRoot(value)
            return HashableWrapper(n)
        elif isinstance(root, list):
            n = []
            for value in root:
                n.append(self.wrapRoot(value))
            return HashableWrapper(n)
        elif isinstance(root, tuple):
            n = tuple([self.wrapRoot(value) for value in root])
            return HashableWrapper(n)
        else:
            return root

    def incrementByteCount(self, field, incr=1):
        self.byteCounts = self.byteCounts._replace(**{field:self.byteCounts.__getattribute__(field) + incr})

    def computeOffsets(self, obj, asReference=False, isRoot=False):
        def check_key(key):
            if key is None:
                raise InvalidPlistException('Dictionary keys cannot be null in plists.')
            elif isinstance(key, Data):
                raise InvalidPlistException('Data cannot be dictionary keys in plists.')
            elif not isinstance(key, (six.binary_type, six.text_type)):
                raise InvalidPlistException('Keys must be strings.')
        
        def proc_size(size):
            if size > 0b1110:
                size += self.intSize(size)
            return size
        # If this should be a reference, then we keep a record of it in the
        # uniques table.
        if asReference:
            if obj in self.computedUniques:
                return
            else:
                self.computedUniques.add(obj)
        
        if obj is None:
            self.incrementByteCount('nullBytes')
        elif isinstance(obj, BoolWrapper):
            self.incrementByteCount('boolBytes')
        elif isinstance(obj, Uid):
            size = self.intSize(obj)
            self.incrementByteCount('uidBytes', incr=1+size)
        elif isinstance(obj, six.integer_types):
            size = self.intSize(obj)
            self.incrementByteCount('intBytes', incr=1+size)
        elif isinstance(obj, (float)):
            size = self.realSize(obj)
            self.incrementByteCount('realBytes', incr=1+size)
        elif isinstance(obj, datetime.datetime):    
            self.incrementByteCount('dateBytes', incr=2)
        elif isinstance(obj, Data):
            size = proc_size(len(obj))
            self.incrementByteCount('dataBytes', incr=1+size)
        elif isinstance(obj, (six.text_type, six.binary_type)):
            size = proc_size(len(obj))
            self.incrementByteCount('stringBytes', incr=1+size)
        elif isinstance(obj, HashableWrapper):
            obj = obj.value
            if isinstance(obj, set):
                size = proc_size(len(obj))
                self.incrementByteCount('setBytes', incr=1+size)
                for value in obj:
                    self.computeOffsets(value, asReference=True)
            elif isinstance(obj, (list, tuple)):
                size = proc_size(len(obj))
                self.incrementByteCount('arrayBytes', incr=1+size)
                for value in obj:
                    asRef = True
                    self.computeOffsets(value, asReference=True)
            elif isinstance(obj, dict):
                size = proc_size(len(obj))
                self.incrementByteCount('dictBytes', incr=1+size)
                for key, value in six.iteritems(obj):
                    check_key(key)
                    self.computeOffsets(key, asReference=True)
                    self.computeOffsets(value, asReference=True)
        else:
            raise InvalidPlistException("Unknown object type.")

    def writeObjectReference(self, obj, output):
        """Tries to write an object reference, adding it to the references
           table. Does not write the actual object bytes or set the reference
           position. Returns a tuple of whether the object was a new reference
           (True if it was, False if it already was in the reference table)
           and the new output.
        """
        position = self.positionOfObjectReference(obj)
        if position is None:
            self.writtenReferences[obj] = len(self.writtenReferences)
            output += self.binaryInt(len(self.writtenReferences) - 1, bytes=self.trailer.objectRefSize)
            return (True, output)
        else:
            output += self.binaryInt(position, bytes=self.trailer.objectRefSize)
            return (False, output)

    def writeObject(self, obj, output, setReferencePosition=False):
        """Serializes the given object to the output. Returns output.
           If setReferencePosition is True, will set the position the
           object was written.
        """
        def proc_variable_length(format, length):
            result = six.b('')
            if length > 0b1110:
                result += pack('!B', (format << 4) | 0b1111)
                result = self.writeObject(length, result)
            else:
                result += pack('!B', (format << 4) | length)
            return result
        
        if isinstance(obj, six.text_type) and obj == six.u(''):
            # The Apple Plist decoder can't decode a zero length Unicode string.
            obj = six.b('')
       
        if setReferencePosition:
            self.referencePositions[obj] = len(output)
        
        if obj is None:
            output += pack('!B', 0b00000000)
        elif isinstance(obj, BoolWrapper):
            if obj.value is False:
                output += pack('!B', 0b00001000)
            else:
                output += pack('!B', 0b00001001)
        elif isinstance(obj, Uid):
            size = self.intSize(obj)
            output += pack('!B', (0b1000 << 4) | size - 1)
            output += self.binaryInt(obj)
        elif isinstance(obj, six.integer_types):
            bytes = self.intSize(obj)
            root = math.log(bytes, 2)
            output += pack('!B', (0b0001 << 4) | int(root))
            output += self.binaryInt(obj)
        elif isinstance(obj, float):
            # just use doubles
            output += pack('!B', (0b0010 << 4) | 3)
            output += self.binaryReal(obj)
        elif isinstance(obj, datetime.datetime):
            timestamp = calendar.timegm(obj.utctimetuple())
            timestamp -= apple_reference_date_offset
            output += pack('!B', 0b00110011)
            output += pack('!d', float(timestamp))
        elif isinstance(obj, Data):
            output += proc_variable_length(0b0100, len(obj))
            output += obj
        elif isinstance(obj, six.text_type):
            bytes = obj.encode('utf_16_be')
            output += proc_variable_length(0b0110, len(bytes)//2)
            output += bytes
        elif isinstance(obj, six.binary_type):
            bytes = obj
            output += proc_variable_length(0b0101, len(bytes))
            output += bytes
        elif isinstance(obj, HashableWrapper):
            obj = obj.value
            if isinstance(obj, (set, list, tuple)):
                if isinstance(obj, set):
                    output += proc_variable_length(0b1100, len(obj))
                else:
                    output += proc_variable_length(0b1010, len(obj))
            
                objectsToWrite = []
                for objRef in obj:
                    (isNew, output) = self.writeObjectReference(objRef, output)
                    if isNew:
                        objectsToWrite.append(objRef)
                for objRef in objectsToWrite:
                    output = self.writeObject(objRef, output, setReferencePosition=True)
            elif isinstance(obj, dict):
                output += proc_variable_length(0b1101, len(obj))
                keys = []
                values = []
                objectsToWrite = []
                for key, value in six.iteritems(obj):
                    keys.append(key)
                    values.append(value)
                for key in keys:
                    (isNew, output) = self.writeObjectReference(key, output)
                    if isNew:
                        objectsToWrite.append(key)
                for value in values:
                    (isNew, output) = self.writeObjectReference(value, output)
                    if isNew:
                        objectsToWrite.append(value)
                for objRef in objectsToWrite:
                    output = self.writeObject(objRef, output, setReferencePosition=True)
        return output
    
    def writeOffsetTable(self, output):
        """Writes all of the object reference offsets."""
        all_positions = []
        writtenReferences = list(self.writtenReferences.items())
        writtenReferences.sort(key=lambda x: x[1])
        for obj,order in writtenReferences:
            # Porting note: Elsewhere we deliberately replace empty unicode strings
            # with empty binary strings, but the empty unicode string
            # goes into writtenReferences.  This isn't an issue in Py2
            # because u'' and b'' have the same hash; but it is in
            # Py3, where they don't.
            if six.PY3 and obj == six.u(''):
                obj = six.b('')
            position = self.referencePositions.get(obj)
            if position is None:
                raise InvalidPlistException("Error while writing offsets table. Object not found. %s" % obj)
            output += self.binaryInt(position, self.trailer.offsetSize)
            all_positions.append(position)
        return output
    
    def binaryReal(self, obj):
        # just use doubles
        result = pack('>d', obj)
        return result
    
    def binaryInt(self, obj, bytes=None):
        result = six.b('')
        if bytes is None:
            bytes = self.intSize(obj)
        if bytes == 1:
            result += pack('>B', obj)
        elif bytes == 2:
            result += pack('>H', obj)
        elif bytes == 4:
            result += pack('>L', obj)
        elif bytes == 8:
            result += pack('>q', obj)
        else:
            raise InvalidPlistException("Core Foundation can't handle integers with size greater than 8 bytes.")
        return result
    
    def intSize(self, obj):
        """Returns the number of bytes necessary to store the given integer."""
        # SIGNED
        if obj < 0: # Signed integer, always 8 bytes
            return 8
        # UNSIGNED
        elif obj <= 0xFF: # 1 byte
            return 1
        elif obj <= 0xFFFF: # 2 bytes
            return 2
        elif obj <= 0xFFFFFFFF: # 4 bytes
            return 4
        # SIGNED
        # 0x7FFFFFFFFFFFFFFF is the max.
        elif obj <= 0x7FFFFFFFFFFFFFFF: # 8 bytes
            return 8
        else:
            raise InvalidPlistException("Core Foundation can't handle integers with size greater than 8 bytes.")
    
    def realSize(self, obj):
        return 8
