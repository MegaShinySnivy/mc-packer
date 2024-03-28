
from zipfile import ZipFile
from typing import cast
import argparse
import os

from filesystem import DirectoryReal, DirectoryZip, FileZip
from version import VersionRange, Version, VersionRangePart
from mod_info import ModPack, Mod


def main(args: argparse.Namespace):
    if not os.path.isdir(args.instance):
        if not os.path.isdir(os.path.join(os.getcwd(), args.instance)):
            print("invalid instance directory")
            exit(255)
        else:
            args.instance = os.path.join(os.getcwd(), args.instance)

    pack = ModPack(DirectoryReal(None, args.instance))
    
    print('LOADING PACK')
    if not pack.load():
        return
    if args.versions:
        for modid, version in [override.split('=') for override in args.versions.split(',')]:
            if modid not in pack.mods:
                mod = Mod()
                mod._version = Version.fromString(version)
                mod.filename = '[no file]'
                mod.name = modid
                mod.modid = modid
                pack.mods[modid] = mod
            else:
                pack.mods[modid]._version = Version.fromString(version)

    if args.lies:
        for modid in args.lies.split(','):
            if modid not in pack.mods:
                continue
            mod = pack.mods[modid]
            for dep in mod.dependencies:
                if dep.modid in pack.mods:
                    range_part = VersionRangePart(pack.mods[dep.modid]._version, True)
                    dep.version_reqs = [VersionRange(range_part, range_part)]

    print('VALIDATING PACK')
    validation = pack.validateVersions(verbose=(args.subcommand == "validate"))
    if args.subcommand == "validate":
        if validation:
            print(' -> [PASS]')
        return
    
    if args.subcommand == 'why-depends':
        pack.why_depends(args.modid, args.why_errors)
        return

    print("TESTING PACK")
    pack.identifyBrokenMods(args.error)
    if args.subcommand == 'find-error':
        return

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--override-versions', dest='versions', type=str, help='<modid>=<version>[,<modid>=<version>[,...]]')
    parser.add_argument('--lie-depends', dest='lies', help='lie to the provided mods so they think requirements are met. eg: `<modid>[,<modid>[,...]]`')
    parser.add_argument('instance', type=str, help='the folder of your minecraft profile')
    subparsers = parser.add_subparsers(dest='subcommand', required=True)
    
    validate_parser = subparsers.add_parser('validate', help='validate dependendies in the pack (10-second runtime)')
    find_error_parser = subparsers.add_parser('find-error', help='intelligently disable mods until the mod causing the provided error is found, then re-enable the other mods (very long runtime)')
    find_error_parser.add_argument('error', type=str, help='the error to solve for')
    why_depends_parser = subparsers.add_parser('why-depends', help='show dependencies of the provided modid (10-second runtime)')
    why_depends_parser.add_argument('--errors', action='store_true', help='only print version mismatches', dest='why_errors')
    why_depends_parser.add_argument('modid', type=str, help="the modid to check")

    args = parser.parse_args()
    main(args)
