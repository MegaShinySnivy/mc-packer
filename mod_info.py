
from pygtail import Pygtail  # type: ignore
from attrs import define
from tqdm import tqdm
import toml

from typing import cast, List, Dict, Union, Any, Optional, Set
from zipfile import ZipFile
import io
import os
import re

from filesystem import FileBase, FileReal, DirectoryZip, DirectoryReal, FileZip
from version import VersionRange, Version, BadVersionString


class DependencyFailure(Exception):
    ...


class ModDependency:
    modid: str
    required: bool
    version_reqs: List[VersionRange]

    def __init__(self, modid: str, required: bool, version_range: str):
        self.modid = modid
        self.required = required
        self.version_reqs = VersionRange.fromString(version_range)

    def __str__(self) -> str:
        return ','.join([str(req) for req in self.version_reqs])

    def validateMod(self, mod: 'Mod') -> bool:
        if mod.modid != self.modid:
            return False
        for version_req in self.version_reqs:
            if version_req.contains(mod._version):
                return True
        return False


MANIFEST_MAPPING: Dict[str, Union[str, List[str]]] = {
    'file.jarVersion': [
        'Implementation-Version',
        'Specification-Version',
        'Manifest-Version'
    ],
    # temp solution until I learn where to actually get these from
    'forge_version_range': '*',
    'minecraft_version_range': '*',
}


class Mod:
    filename:       str
    name:           str
    modid:          str
    _version:       Version
    dependencies:   List[ModDependency]
    dependents:     List[ModDependency]
    errors:         List[str]

    pack:           'ModPack'
    manifest:       Dict[str, str]
    toml_data:      Dict[str, Any]
    parent:         Optional['Mod']

    def __init__(self, pack: 'ModPack'):
        self.dependencies = []
        self.dependents = []
        self.errors = []
        self.manifest = {}
        self.pack = pack

    def enable(self) -> None:
        if self.filename.endswith('.jar.disabled'):
            new_name = self.filename.removesuffix('.disabled')
            FileReal(self.pack.directory, self.filename).rename(new_name)
            self.filename = new_name
        if self.filename and self.filename != '[no file]':
            for dep in self.dependencies:
                if dep.modid in self.pack.mods:
                    self.pack.mods[dep.modid].enable()

    def disable(self) -> None:
        if self.filename.endswith('.jar'):
            new_name = self.filename + ".disabled"
            FileReal(self.pack.directory, self.filename).rename(new_name)
            self.filename = new_name
        if self.filename and self.filename != '[no file]':
            for dep in self.dependents:
                if dep.modid in self.pack.mods:
                    self.pack.mods[dep.modid].enable()

    @classmethod
    def load(cls,
                pack: 'ModPack',
                filename: str,
                toml_data: Dict[str, Any],
                manifest: str
            ) -> 'Mod':
        instance = cls(pack)
        instance.filename = filename

        if manifest != "":
            manifest = manifest.replace('\r\n', '\n')
            while '\n\n' in manifest:
                manifest = manifest.replace('\n\n', '\n')

            for line in manifest.split('\n'):
                parts = line.split(':')
                if len(parts) == 2:
                    instance.manifest[parts[0].strip()] = parts[1].strip()

        def processExternalField(field_raw: str) -> str:
            # checks if string is an external reference `${<var_name>}`
            extern = re.match(r'\${([^}]+)}', field_raw)
            if not extern:
                return field_raw

            field = cast(str, extern.groups(1)[0])
            map = MANIFEST_MAPPING.get(field, None)

            if type(map) is str:
                return map
            elif type(map) is list:
                result: str = ""
                for key in map:

                    result = instance.manifest.get(key, "")
                    if result:
                        break

                if result == "":
                    raise ValueError(
                        f"failed to process field value {field_raw}"
                    )
                return result

            elif map is None:
                return field_raw
            else:
                raise ValueError(f"failed to process field value {field_raw}")

        if "mods" in toml_data and len(toml_data['mods']) > 0:
            mod = toml_data['mods'][0]

            instance.modid = processExternalField(mod['modId'])
            instance._version = Version.fromString(
                processExternalField(mod['version'])
            )
            instance.name = processExternalField(mod["displayName"])
            instance.toml_data = toml_data

            toml_deps_len = len(toml_data["dependencies"])
            if "dependencies" in toml_data and toml_deps_len > 0:
                deps = toml_data["dependencies"]
                if instance.modid in deps and len(deps[instance.modid]) > 0:
                    for dependency in deps[instance.modid]:
                        try:
                            version_range = processExternalField(
                                dependency['versionRange']
                            )
                            instance.dependencies.append(
                                ModDependency(
                                    dependency["modId"],
                                    dependency['mandatory'],
                                    version_range
                                )
                            )
                        except BadVersionString as e:
                            instance.errors.append(
                                f"'{instance.name}' dependency "
                                f"'{dependency['modId']}' has invalid "
                                f"version range '{dependency['versionRange']}'"
                            )

        return instance


class DependencyGraph:
    _ALL_GRAPHS:    Dict[str, 'DependencyGraph'] = {}
    _ALL_NODES:     Dict[str, 'Node'] = {}

    class Node:
        mod_set:    Set[Mod]
        graph:      'DependencyGraph'

        def __init__(self, mod: Mod, graph: 'DependencyGraph'):
            self.mod_set = {mod}
            self.graph = graph
            if mod.modid in DependencyGraph._ALL_NODES:
                raise ValueError(f"modid '{mod.modid}' already has a node")

        def merge(self, other: 'DependencyGraph.Node') -> None:
            self.mod_set.union(other.mod_set)
            for mod in other.mod_set:
                DependencyGraph._ALL_GRAPHS[mod.modid] = self.graph
                DependencyGraph._ALL_NODES[mod.modid] = self
            other.mod_set = set()

        @property
        def dependencies(self) -> List[ModDependency]:
            deps = []
            for mod in self.mod_set:
                deps.extend(mod.dependencies)
            return deps

        @property
        def dependents(self) -> List[ModDependency]:
            deps = []
            for mod in self.mod_set:
                deps.extend(mod.dependents)
            return deps

    nodes: List[Node]

    def __init__(self, mod: Mod):
        self.nodes = [DependencyGraph.Node(mod, self)]

    def merge(self, other: 'DependencyGraph') -> None:
        for node in other.nodes:
            for mod in node.mod_set:
                DependencyGraph._ALL_GRAPHS[mod.modid] = self
                DependencyGraph._ALL_NODES[mod.modid] = node
            node.graph = self
            self.nodes.append(node)
        other.nodes = []

    def disable_all(self) -> None:
        for node in self.nodes:
            for mod in node.mod_set:
                mod.disable()

    def enable_all(self) -> None:
        for node in self.nodes:
            for mod in node.mod_set:
                mod.enable()


class ModPack:
    directory:  DirectoryReal
    mods:       Dict[str, Mod]
    errors:     List[str]

    def __init__(self, directory: DirectoryReal):
        self.directory = directory
        self.mods = {}
        self.errors = []

    def process_jar(self, jar: DirectoryZip) -> bool:
        found = False

        for item in [x for x in jar.list() if x.name.endswith('.jar')]:
            with io.BytesIO(
                        cast(ZipFile, jar._zip).read(item.name)
                    ) as nested_jar_bytes:
                with ZipFile(nested_jar_bytes, 'r') as nested_jar:
                    _dir = DirectoryZip(jar, item.name, nested_jar)
                    found = found or self.process_jar(_dir)  # yay recursion

        if jar.has("META-INF/mods.toml"):
            found = True
            toml_data = toml.loads(
                FileZip("META-INF/mods.toml", jar).read().decode()
            )
            manifest = ""
            if jar.has("META-INF/MANIFEST.MF"):
                manifest = FileZip(
                    "META-INF/MANIFEST.MF",
                    jar
                ).read().decode()

            mod = Mod.load(self, jar.full_path, toml_data, manifest)
            if hasattr(mod, 'modid'):
                self.mods[mod.modid] = mod
        return found

    def load(self) -> bool:
        mod_dir = DirectoryReal(self.directory, 'mods')
        # for file in self.directory.list():
        for file in tqdm(mod_dir.list()):
            if not issubclass(type(file), FileBase):
                continue
            file = cast(FileBase, file)
            if file.name.endswith('.disabled'):
                continue

            with ZipFile(
                        os.path.join(mod_dir.full_path, file.name),
                        'r'
                    ) as jar:
                result = self.process_jar(
                    DirectoryZip(mod_dir, file.name, jar)
                )
                if not result:
                    self.errors.append(
                        f"Failed to locate mod in jar '{file.name}'"
                    )
                    # return False
        return True

    def validateVersions(self, verbose: bool) -> bool:
        for mod in self.mods.values():
            for dep in mod.dependencies:
                if dep.modid in self.mods:
                    dependency = self.mods[dep.modid]
                    if not dep.validateMod(dependency):
                        dependency.errors.append(
                            f"'{mod.modid}' requires '{dep.version_reqs}'"
                        )

                    rdep_mod = ModDependency(mod.modid, False, '*')
                    rdep_mod.version_reqs = dep.version_reqs
                    dependency.dependents.append(rdep_mod)

                else:
                    if dep.required and dep.modid not in []:
                        mod.errors.append(
                            f"Could not find mod '{dep.modid}'! "
                            f"requirements: {dep.version_reqs}"
                        )

        err_num = 0
        for mod in self.mods.values():
            if len(mod.errors) > 0:
                err_num += 1
                if verbose:
                    print(f'{mod.name} ({mod.modid}) {mod._version}:')
                    print(f' ->  [file]: {mod.filename}')
                    for error in mod.errors:
                        print(f' --> {error}')
                    print()

        for error in self.errors:
            err_num += 1
            if verbose:
                print(f' -> {error}')

        return err_num == 0

    def why_depends(self, modid: str, error: bool) -> None:
        if modid not in self.mods:
            print('==================================')
            print(f'why-depends: modid "{modid}" not found!\n')
            return

        mod = self.mods[modid]
        print(f'{mod.name} ({modid}) [{mod._version}]:')
        print(f' -> File: "{mod.filename}"\n')
        print(f' -> Dependencies')
        for dep in mod.dependencies:
            vers_reqs_met = any(
                [range.contains(mod._version) for range in dep.version_reqs]
            )
            if not error or (error and not vers_reqs_met):
                dep_mod = self.mods.get(dep.modid, None)
                dep_name = dep_mod.name if dep_mod else dep.modid
                dep_installed = dep.modid in self.mods
                print(f'   -> name:      {dep_name}')
                print(f'   -> modid:     {dep.modid}')
                print(f'   -> required:  {"yes" if dep.required else "no"}')
                print(f'   -> installed: {"yes" if dep_installed else "no"}')
                print(f'   -> versions:  {dep.version_reqs}')
                print()

        print(f' -> Dependents')
        for dep in mod.dependents:
            vers_reqs_met = any(
                [range.contains(mod._version) for range in dep.version_reqs]
            )
            if not error or (error and not vers_reqs_met):
                dep_mod = self.mods.get(dep.modid, None)
                dep_name = dep_mod.name if dep_mod else dep.modid
                dep_installed = dep.modid in self.mods
                print(f'   -> name:      {dep_name}')
                print(f'   -> modid:     {dep.modid}')
                # print(f'   -> required: {dep.required}')
                print(f'   -> installed: {"yes" if dep_installed else "no"}')
                print(f'   -> versions:  {dep.version_reqs}')
                print()

    def run(self) -> bool:
        return False

    def identifyBrokenMods(self, error: str) -> bool:
        graphs: List[DependencyGraph] = []

        for mod in self.mods.values():
            if mod.modid in ['minecraft', 'forge']:
                continue
            graph = DependencyGraph(mod)
            graphs.append(graph)
            DependencyGraph._ALL_NODES[mod.modid] = graph.nodes[0]
            DependencyGraph._ALL_GRAPHS[mod.modid] = graph

        # TODO: Merge circular node paths into a single node each

        def process_graph(graph: DependencyGraph):
            for node in graph.nodes:
                for dep in node.dependents:
                    invalid_modid = dep.modid in ['minecraft', 'forge']
                    not_installed = dep.modid not in self.mods
                    if invalid_modid or (not dep.required and not_installed):
                        continue
                    mod_graph = DependencyGraph._ALL_GRAPHS[mod.modid]
                    dep_graph = DependencyGraph._ALL_GRAPHS[dep.modid]
                    if mod_graph is not dep_graph:
                        mod_graph.merge(dep_graph)
                        process_graph(dep_graph)
                for dep in node.dependencies:
                    invalid_modid = dep.modid in ['minecraft', 'forge']
                    not_installed = dep.modid not in self.mods
                    if invalid_modid or (not dep.required and not_installed):
                        continue
                    mod_graph = DependencyGraph._ALL_GRAPHS[mod.modid]
                    dep_graph = DependencyGraph._ALL_GRAPHS[dep.modid]
                    if mod_graph is not dep_graph:
                        mod_graph.merge(dep_graph)
                        process_graph(dep_graph)

        for mod in self.mods.values():
            if mod.modid in ['minecraft', 'forge']:
                continue
            process_graph(DependencyGraph._ALL_GRAPHS[mod.modid])

        graph_list: List[DependencyGraph] = []
        for node in DependencyGraph._ALL_NODES.values():
            if node.graph not in graph_list:
                graph_list.append(node.graph)
        # sort by number of mods in graph
        graph_list = sorted(
            graph_list,
            key=(lambda x: sum([len(y.mod_set) for y in x.nodes]))
        )

        for i, graph in enumerate(graph_list):
            print('==================================')
            mod_count = sum([len(y.mod_set) for y in graph.nodes])
            print(f'Graph {i} ({mod_count} mods):')
            for node in graph.nodes:
                for mod in node.mod_set:
                    print(f" -> '{mod.modid}'")
            print()

        print(f'total loaded mods: {len(self.mods)}')
        print(f'total separate graphs: {len(graph_list)}')

        missing_count = 0
        for modid in self.mods.keys():
            invalid_modid = modid in ['minecraft', 'forge']
            mod_installed = modid in DependencyGraph._ALL_NODES.keys()
            if not mod_installed and not invalid_modid:
                missing_count += 1
                mod_name = self.mods[modid].name
                print(f'Missing graph for mod "{mod_name}" ({modid})')
        print(f'Missing graphs for {missing_count} mods')

        logs = DirectoryReal(self.directory, "logs")

        error_files = ['latest.log', 'debug.log', 'latest_stdout.log']
        search_filename = ''
        for candidate in error_files:
            log_exists = logs.has(candidate)
            log = FileReal(logs, candidate)
            log_has_error = error in log.read().decode(errors="ignore")
            if log_exists and log_has_error:
                search_filename = candidate

        if search_filename:
            print(f'Scanning "{search_filename}"')
        else:
            print('Scanning all')

        # TODO: Determine which graph is causing the provided error
        # by disabling half the remaining graphs each time until a
        # single graph is left

        # find the only True value in the list
        # number of iterations = int(ceil(log2(len(graph_list))))
        def binaryGraphElimination(_list: List[DependencyGraph]) -> int:
            __list = [DependencyGraph(Mod(self))] + _list
            left = 0
            right = len(__list) - 1

            while left <= right:
                mid = (left + right) // 2
                # TODO: Disable graphs in __list[mid:]
                for graph in __list[mid:]:
                    graph.disable_all()
                result = self.run()  # return True if run occurs successfully
                if any(__list[mid:]):
                    left = mid + 1
                else:
                    right = mid - 1

            return right - 1

        # bad_graph1 = binaryGraphElimination(graph_list)
        # bad_graph2 = None

        # if bad_graph1 >= 0:
        #     graph_list.remove(bad_graph1)
        #     bad_graph2 = binaryElimination(graph_list)
        # else:
        #     ... # no error??

        # if bad_graph2 >= 0:
        #     bad_mod1 = find_bad_mod(bad_graph1)
        #     bad_mod2 = find_bad_mod(bad_graph2)
        #     report_mod_conflict(bad_mod1, bad_mod2)
        # else:
        #     bad_mod1 = find_bad_mod(bad_graph1)
        #     bad_mod2 = None
        #     if bad_mod1 >= 0:
        #         bad_graph1.freeze(bad_mod1)
        #         bad_mod2 = find_bad_mod(bad_graph1)
        #         if bad_mod2:
        #             report_mod_conflict(bad_mod1, bad_mod2)
        #         else:
        #             report_bad_mod(bad_mod1)
        #     else:
        #         ... # no error??

        # TODO: Sort the remaining graph, then disable the leaves,
        # and iterate to each of the parents if all of that parent's
        # children have been visited

        return True
