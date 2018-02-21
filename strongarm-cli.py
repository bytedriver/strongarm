# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function

import sys
import argparse
from ctypes import sizeof

from strongarm.macho import MachoParser, MachoBinary, MachoAnalyzer, ObjcCategory, ObjcClass
from strongarm.macho import CPU_TYPE, DylibCommand
from strongarm.debug_util import DebugUtil
from strongarm.objc import CodeSearch, CodeSearchTermCallDestination, RegisterContentsType, ObjcFunctionAnalyzer, \
    ObjcBranchInstruction


def pick_macho_slice(parser: MachoParser) -> MachoBinary:
    """Retrieve a MachoBinary slice from a MachoParser, with a preference for an arm64 slice
    """
    binary_slices = parser.slices

    # Sanity checks
    if not parser or len(binary_slices) == 0:
        raise ValueError('Could not parse {} as a Mach-O or FAT'.format(parser.filename))

    parsed_binary = None
    if len(binary_slices) == 1:
        # only one slice - return that
        parsed_binary = binary_slices[0]
    else:
        # multiple slices - return 64 bit slice if there is one
        for slice in binary_slices:
            parsed_binary = slice
            if parsed_binary.cpu_type == CPU_TYPE.ARM64:
                break
    return parsed_binary


def print_header(args) -> None:
    header_lines = [
        '\nstrongarm - Mach-O analyzer',
        '{}'.format(args.binary_path),
    ]
    # find longest line
    longest_line_len = 0
    for line in header_lines:
        longest_line_len = max(longest_line_len, len(line))
    # add a line of hyphens, where the hyphen count matches the longest line
    header_lines.append('-' * longest_line_len)
    header_lines.append('')

    # print header
    for line in header_lines:
        print(line)


parser = argparse.ArgumentParser(description='Mach-O Analyzer')
parser.add_argument(
    '--verbose', action='store_true', help=
    'Output extra info while analyzing'
)
parser.add_argument(
    'binary_path', metavar='binary_path', type=str, help=
    'Path to binary to analyze'
)
args = parser.parse_args()

if args.verbose:
    DebugUtil.debug = True

print_header(args)

parser = MachoParser(args.binary_path)

# print slice info
print('Slices:')
for macho_slice in parser.slices:
    print('\t{} Mach-O slice @ {}'.format(macho_slice.cpu_type.name, hex(macho_slice._offset_within_fat)))

binary = pick_macho_slice(parser)
analyzer = MachoAnalyzer.get_analyzer(binary)

print('Reading {} slice'.format(binary.cpu_type.name))

endianness = 'Big' if binary.is_swap else 'Little'
endianness = '{} endian'.format(endianness)
print(endianness)
print('Virtual base: {}'.format(hex(binary.get_virtual_base())))

print('\nLoad commands:')
load_commands = binary.load_dylib_commands
for cmd in load_commands:
    dylib_load_string_fileoff = cmd.fileoff + cmd.dylib.name.offset
    dylib_load_string_len = cmd.cmdsize - cmd.dylib.name.offset
    dylib_load_string_bytes = binary.get_bytes(dylib_load_string_fileoff, dylib_load_string_len)
    # trim anything after NUL character
    dylib_load_string_bytes = dylib_load_string_bytes.split(b'\0')[0]
    dylib_load_string = dylib_load_string_bytes.decode('utf-8')

    dylib_version = cmd.dylib.current_version
    print('\t{} v.{}'.format(dylib_load_string, hex(dylib_version)))

print('\nSegments:')
for segment, cmd in binary.segment_commands.items():
    print('\t{} @ [{} - {}]'.format(segment, hex(cmd.vmaddr), hex(cmd.vmaddr + cmd.vmsize)))

print('\nSections:')
print('\tContains encrypted section? {}'.format(binary.is_encrypted()))
for section, cmd in binary.sections.items():
    print('\t{} @ [{} - {}]'.format(section, hex(cmd.address), hex(cmd.end_address)))

print('\nSymbols:')
print('\tImported symbols:')
stub_map = analyzer.external_symbol_names_to_branch_destinations
for imported_sym in analyzer.imported_symbols:
    print('\t\t{}'.format(imported_sym))
    # attempt to find the call stub for this symbol
    if imported_sym in stub_map:
        print('\t\t\tCallable dyld stub @ {}'.format(hex(stub_map[imported_sym])))

print('\tExported symbols:')
for exported_sym in analyzer.exported_symbols:
    print('\t\t{}'.format(exported_sym))

print('\nObjective-C Methods:')
methods = analyzer.get_objc_methods()
for method_info in methods:
    # belongs to a class or category?
    if isinstance(method_info.objc_class, ObjcCategory):
        category = method_info.objc_class   # type: ObjcCategory
        class_name = '{} ({})'.format(category.base_class, category.name)
    else:
        class_name = method_info.objc_class.name

    print('\t-[{} {}] defined at {}'.format(class_name,
                                            method_info.objc_sel.name,
                                            hex(method_info.objc_sel.implementation)))


from capstone import CsInsn
from capstone.arm64 import Arm64Op, ARM64_OP_REG, ARM64_OP_IMM, ARM64_OP_MEM

from typing import Text


def format_instruction_arg(instruction: CsInsn, arg: Arm64Op) -> Text:
    if arg.type == ARM64_OP_REG:
        return instruction.reg_name(arg.value.reg)
    elif arg.type == ARM64_OP_IMM:
        return hex(arg.value.imm)
    elif arg.type == ARM64_OP_MEM:
        return '[{} #{}]'.format(instruction.reg_name(arg.mem.base), hex(arg.mem.disp))
    raise RuntimeError('unknown arg type {}'.format(arg.type))


while True:
    print('Enter a SEL to disassemble:')
    desired_sel = input()
    try:
        desired_imp = [x for x in methods if x.objc_sel.name == desired_sel][0]
    except IndexError:
        print('Unknown SEL {}'.format(desired_sel))
        continue

    print('-[{} {}]'.format(desired_imp.objc_class.name, desired_imp.objc_sel.name))
    function_analyzer = ObjcFunctionAnalyzer.get_function_analyzer(binary, desired_imp.imp_addr)

    for instr in function_analyzer.instructions:
        instruction_string = '\t{}\t\t{}'.format(hex(instr.address), instr.mnemonic)
        # add each arg to the string
        for arg in instr.operands:
            instruction_string += ' ' + format_instruction_arg(instr, arg)

        instruction_string += '\t\t\t'
        # parse as an ObjcInstruction
        wrapped_instr = function_analyzer.get_instruction_at_address(instr.address)
        if wrapped_instr.symbol:
            instruction_string += '#\t'
            instruction_string += wrapped_instr.symbol

            if isinstance(wrapped_instr, ObjcBranchInstruction):
                # TODO(PT): count args by counting colons in selector name
                if wrapped_instr.selector:
                    instruction_string += '(id, @selector({}));'.format(wrapped_instr.selector.name)

                for i in range(2, 4):
                    register = 'x{}'.format(i)
                    method_arg = function_analyzer.get_register_contents_at_instruction(register, wrapped_instr)
                    instruction_string += hex(method_arg)

        print(instruction_string)
