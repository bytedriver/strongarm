from enum import IntEnum
from ctypes import BigEndianStructure, c_uint8, c_uint32

from strongarm.macho.arch_independent_structs import ArchIndependentStructure


class CodesignBlobTypeEnum(IntEnum):
    """Magic numbers for codesigning blobs
    """
    CSMAGIC_REQUIREMENT = 0xfade0c00            # single requirement blob
    CSMAGIC_REQUIREMENT_SET = 0xfade0c01        # requirements vector (internal requirements)
    CSMAGIC_CODE_DIRECTORY = 0xfade0c02         # CodeDirectory blob
    CSMAGIC_EMBEDDED_SIGNATURE = 0xfade0cc0     # embedded signature data
    CSMAGIC_DETACHED_SIGNATURE = 0xfade0cc1     # multi-arch collection of embedded signatures
    CSMAGIC_EMBEDDED_ENTITLEMENTS = 0xfade7171  # embedded entitlements
    CSMAGIC_BLOBWRAPPER = 0xfade0b01            # CMS signature, "among other things" from the source code


class CSBlobStruct(BigEndianStructure):
    """Basic CodeSign blob structure. These fields shared by all CodeSign blob structures.
    """
    _fields_ = [
        ('magic', c_uint32),
        ('length', c_uint32)
    ]


class CSSuperblobStruct(BigEndianStructure):
    _fields_ = CSBlobStruct._fields_ + [
        ('index_entry_count', c_uint32)
    ]


class CSCodeDirectoryStruct(BigEndianStructure):
    _fields_ = CSBlobStruct._fields_ + [
        ('version', c_uint32),
        ('flags', c_uint32),
        ('hash_offset', c_uint32),
        ('identifier_offset', c_uint32),
        ('special_slots_count', c_uint32),
        ('code_slots_count', c_uint32),
        ('code_limit', c_uint32),
        ('hash_size', c_uint8),
        ('hash_type', c_uint8),
        ('platform', c_uint8),
        ('page_size', c_uint8),
        ('unused', c_uint32),
        ('scatter_offset', c_uint32),
        ('team_offset', c_uint32),
    ]


class CSBlobIndexStruct(BigEndianStructure):
    _fields_ = [
        ('type', c_uint32),
        ('offset', c_uint32)
    ]


class CSBlob(ArchIndependentStructure):
    _32_BIT_STRUCT = CSBlobStruct
    _64_BIT_STRUCT = CSBlobStruct


class CSSuperblob(ArchIndependentStructure):
    _32_BIT_STRUCT = CSSuperblobStruct
    _64_BIT_STRUCT = CSSuperblobStruct


class CSCodeDirectory(ArchIndependentStructure):
    _32_BIT_STRUCT = CSCodeDirectoryStruct
    _64_BIT_STRUCT = CSCodeDirectoryStruct


class CSBlobIndex(ArchIndependentStructure):
    _32_BIT_STRUCT = CSBlobIndexStruct
    _64_BIT_STRUCT = CSBlobIndexStruct
