# -*- coding: utf-8 -*-
from strongarm.macho.macho_binary import MachoBinary

from .codesign_definitions import (
    CodesignBlobTypeEnum,
    CSBlob,
    CSSuperblob,
    CSCodeDirectory,
    CSBlobIndex
)


class CodesignParser:
    def __init__(self, binary: MachoBinary):
        self.binary = binary
        self.entitlements: bytearray = None
        self.signing_identifier: str = None
        self.signing_team_id: str = None

        self._codesign_entry = self.binary.code_signature.dataoff
        self.parse_codesign_blob(self._codesign_entry)

    def read_32_big_endian(self, offset: int) -> int:
        """Read a 32-bit word from the file offset in big-endian order.
        """
        word_bytes = self.binary.get_bytes(offset, 4)
        word = int.from_bytes(word_bytes, byteorder='big')
        return word

    def parse_codesign_blob(self, file_offset: int) -> None:
        """High-level parser to parse the codesign blob at the file offset.
        """
        magic = self.read_32_big_endian(file_offset)

        if magic == CodesignBlobTypeEnum.CSMAGIC_CODE_DIRECTORY:
            self.parse_code_directory(file_offset)
        elif magic == CodesignBlobTypeEnum.CSMAGIC_EMBEDDED_SIGNATURE:
            self.parse_superblob(file_offset)
        elif magic == CodesignBlobTypeEnum.CSMAGIC_EMBEDDED_ENTITLEMENTS:
            self.entitlements = self.parse_entitlements(file_offset)
        elif magic == CodesignBlobTypeEnum.CSMAGIC_REQUIREMENT:
            pass
        elif magic == CodesignBlobTypeEnum.CSMAGIC_REQUIREMENT_SET:
            pass
        elif magic == CodesignBlobTypeEnum.CSMAGIC_DETACHED_SIGNATURE:
            pass
        elif magic == CodesignBlobTypeEnum.CSMAGIC_BLOBWRAPPER:
            pass
        else:
            # unknown magic
            raise RuntimeError(f'Unknown CodeSign blob magic: {hex(magic)}')

    def parse_superblob(self, file_offset: int):
        """Parse a codesign 'superblob' at the provided file offset.
        This is a blob which embeds several child blobs.
        The superblob format is the superblob header, followed by several csblob_index structures describing
        the layout of the child blobs.
        """
        superblob = CSSuperblob(self.binary, file_offset, virtual=False)
        if superblob.magic != CodesignBlobTypeEnum.CSMAGIC_EMBEDDED_SIGNATURE:
            raise RuntimeError(f'Can blobs other than embedded signatures be superblobs? {hex(superblob.magic)}')

        # move past the superblob header to the first index struct entry
        file_offset += superblob.sizeof
        for i in range(superblob.index_entry_count):
            csblob_index = self.parse_csblob_index(file_offset)
            csblob_file_offset = self._codesign_entry + csblob_index.offset

            # parse the blob we learned about
            self.parse_codesign_blob(csblob_file_offset)

            # iterate to the next blob index struct in list
            file_offset += csblob_index.sizeof

    @staticmethod
    def get_index_blob_name(blob_index: CSBlobIndex):
        """Get the human-readable blob type from the `type` field in a CSBlobIndex.
        """
        # cs_blobs.h
        blob_types = {0: 'Code Directory',
                      1: 'Info slot',
                      2: 'Requirement Set',
                      3: 'Resource Directory',
                      4: 'Application',
                      5: 'Embedded Entitlements',
                      0x1000: 'Alternate Code Directory',
                      0x10000: 'CMS Signature'}
        return blob_types[blob_index.type]

    def parse_csblob_index(self, file_offset: int) -> CSBlobIndex:
        """Parse a csblob_index at the file offset.
        A csblob_index is a header structure describing the type/layout of a superblob's child blob.
        This method will parse and return the index header.
        """
        return CSBlobIndex(self.binary, file_offset, virtual=False)

    def parse_code_directory(self, file_offset: int):
        """Parse a Code Directory at the file offset.
        """
        code_directory = CSCodeDirectory(self.binary, file_offset, virtual=False)

        identifier_address = code_directory.binary_offset + code_directory.identifier_offset
        identifier_string = self.binary.get_full_string_from_start_address(identifier_address, virtual=False)
        self.signing_identifier = identifier_string

        # Version 0x20100+ includes scatter_offset
        # Version 0x20200+ includes team offset
        if code_directory.version >= 0x20200:
            # Note that if the version < 0x20200, the CSCodeDirectory structure parses past the end of the actual struct
            team_id_address = code_directory.binary_offset + code_directory.team_offset
            team_id_string = self.binary.get_full_string_from_start_address(team_id_address, virtual=False)
            self.signing_team_id = team_id_string

    def parse_entitlements(self, file_offset: int) -> bytearray:
        """Parse the embedded entitlements blob at the file offset.
        Returns a bytearray of the embedded entitlements.
        """
        entitlements_blob = CSBlob(self.binary, file_offset, virtual=False)
        if entitlements_blob.magic != CodesignBlobTypeEnum.CSMAGIC_EMBEDDED_ENTITLEMENTS:
            raise RuntimeError(f'incorrect magic for embedded entitlements: {hex(entitlements_blob.magic)}')
        blob_end = entitlements_blob.binary_offset + entitlements_blob.length

        xml_start = file_offset + entitlements_blob.sizeof
        xml_length = blob_end - xml_start
        xml = self.binary.get_bytes(xml_start, xml_length)
        return xml
