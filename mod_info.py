
from pygtail import Pygtail # type: ignore
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


class DependencyFailure(Exception): ...

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
    'file.jarVersion': ['Implementation-Version', 'Specification-Version', 'Manifest-Version'],
    'forge_version_range': '*',
    'minecraft_version_range': '*'
}

class Mod:
    filename:       str
    name:           str
    modid:          str
    _version:       Version
    dependencies:   List[ModDependency]
    dependents:     List[ModDependency]
    errors:         List[str]

    manifest:       Dict[str, str]
    toml_data:      Dict[str, Any]
    parent:         Optional['Mod']

    def __init__(self):
        self.dependencies = []
        self.dependents = []
        self.errors = []
        self.manifest = {}

    @classmethod
    def load(cls, filename: str, toml_data: Dict[str, Any], manifest: str) -> 'Mod':
        instance = cls()
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
            extern = re.match(r'\${([^}]+)}', field_raw) # checks if string is an external reference `${<var_name>}`
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
                    raise ValueError(f"failed to process field value {field_raw}")
                return result
            
            elif map == None:
                return field_raw
            else:
                raise ValueError(f"failed to process field value {field_raw}")

        if "mods" in toml_data and len(toml_data['mods']) > 0:
            mod = toml_data['mods'][0]

            instance.modid = processExternalField(mod['modId'])
            instance._version = Version.fromString(processExternalField(mod['version']))
            instance.name = processExternalField(mod["displayName"])
            instance.toml_data = toml_data

            if "dependencies" in toml_data and len(toml_data["dependencies"]) > 0:
                deps = toml_data["dependencies"]
                if instance.modid in deps and len(deps[instance.modid]) > 0:
                    for dependency in deps[instance.modid]:
                        try:
                            version_range = processExternalField(dependency['versionRange'])
                            instance.dependencies.append(ModDependency(dependency["modId"], dependency['mandatory'], version_range))
                        except BadVersionString as e:
                            instance.errors.append(f"'{instance.name}' dependency '{dependency['modId']}' has invalid version range '{dependency['versionRange']}'")

        return instance

class DependencyGraph:
    _ALL_GRAPHS:    List['DependencyGraph'] = []
    _ALL_DEPS:      Dict[str, 'Node'] = {}

    class Node:
        mod_list:   List[Mod]
        graph:      'DependencyGraph'

        def __init__(self, mod: Mod, graph: 'DependencyGraph'):
            self.mod_list = [mod]
            self.graph = graph
            if mod.modid in DependencyGraph._ALL_DEPS:
                raise ValueError(f"modid '{mod.modid}' already has a node")

        # def enable(self):
        #     for mod in self.mod_list:
        #         mod.enable()

    nodes: List[Node]

    def __init__(self, mod: Mod):
        self.nodes = [DependencyGraph.Node(mod, self)]

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
        for item in [x for x in jar.list() if x.name.startswith('META-INF/jarjar/') and x.name.endswith('.jar')]:
            with io.BytesIO(cast(ZipFile, jar._zip).read(item.name)) as nested_jar_bytes:
                with ZipFile(nested_jar_bytes, 'r') as nested_jar:
                    _dir = DirectoryZip(jar, item.name, nested_jar)
                    found = found or self.process_jar(_dir) # yay recursion
                    
        if jar.has("META-INF/mods.toml"):
            found = True
            toml_data = toml.loads(FileZip("META-INF/mods.toml", jar).read().decode())
            manifest = ""
            if jar.has("META-INF/MANIFEST.MF"):
                manifest = FileZip("META-INF/MANIFEST.MF", jar).read().decode()

            mod = Mod.load(jar.full_path, toml_data, manifest)
            if hasattr(mod ,'modid'):
                self.mods[mod.modid] = mod
        return found

    def load(self) -> bool:
        mod_dir = DirectoryReal(self.directory, 'mods')
        for file in tqdm(mod_dir.list()):
        # for file in self.directory.list():
            if not issubclass(type(file), FileBase):
                continue
            file = cast(FileBase, file)
            if file.name.endswith('.disabled'):
                continue

            with ZipFile(os.path.join(mod_dir.full_path, file.name), 'r') as jar:
                result = self.process_jar(DirectoryZip(mod_dir, file.name, jar))
                if not result:
                    self.errors.append(f"Failed to locate mod in jar '{file.name}'")
                    # return False
        return True

    def validateVersions(self, verbose: bool) -> bool:
        for mod in self.mods.values():
            for dep in mod.dependencies:
                if dep.modid in self.mods:
                    dependency = self.mods[dep.modid]
                    if not dep.validateMod(dependency):
                        dependency.errors.append(f"'{mod.modid}' requires '{dep.version_reqs}'")

                    rdep_mod = ModDependency(mod.modid, False, '*')
                    rdep_mod.version_reqs = dep.version_reqs
                    dependency.dependents.append(rdep_mod)

                else:
                    if dep.required and not dep.modid in []:
                        mod.errors.append(f"Could not find mod '{dep.modid}'! requirements: {dep.version_reqs}")

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
        if not modid in self.mods:
            print('==================================')
            print(f'why-depends: modid "{modid}" not found!\n')
            return

        mod = self.mods[modid]
        print(f'{mod.name} ({modid}) [{mod._version}]:')
        print(f' -> Dependencies')
        for dep in mod.dependencies:
            if not error or (error and not any([range.contains(mod._version) for range in dep.version_reqs])):
                dep_mod = self.mods.get(dep.modid, None)
                dep_name = dep_mod.name if dep_mod else dep.modid
                print(f'   -> name:     {dep_name}')
                print(f'   -> modid:    {dep.modid}')
                print(f'   -> versions: {dep.version_reqs}')
                print()
        
        print(f' -> Dependents')
        for dep in mod.dependents:
            if not error or (error and not any([range.contains(mod._version) for range in dep.version_reqs])):
                dep_mod = self.mods.get(dep.modid, None)
                dep_name = dep_mod.name if dep_mod else dep.modid
                print(f'   -> name:     {dep_name}')
                print(f'   -> modid:    {dep.modid}')
                print(f'   -> versions: {dep.version_reqs}')
                print()

    def run(self) -> None: ...

    def identifyBrokenMods(self, error: str) -> bool:
        graphs: List[DependencyGraph] = []

        print(f'total loaded mods: {len(self.mods)}')

        # find each "leaf" mod (has no dependents)
        for mod in self.mods.values():
            if len(mod.dependents) == 0:
                graph = DependencyGraph(mod)
                graphs.append(graph)
                # DependencyGraph._ALL_DEPS[mod.modid] = graph.nodes[0]

        print(f'total leaf mods: {len(graphs)}')

        def process_node(node: DependencyGraph.Node):
            for mod in node.mod_list:
                if mod.modid in ['forge', 'minecraft']:
                    continue
                if mod.modid == 'create':
                    print('found create')
                # print(mod.modid)
                for dep in mod.dependents:
                    if dep.modid in ['forge', 'minecraft']:
                        continue
                    # if mod hasn't been processed and mod exists:
                    if dep.required and not dep.modid in DependencyGraph._ALL_DEPS and dep.modid in self.mods:
                        dep_mod = self.mods[dep.modid]
                        # mods with circular dependencies are collapsed into a single node (unlikely but possible)
                        if mod.modid in [x.modid for x in dep_mod.dependents]:
                            node.mod_list.append(dep_mod)
                            DependencyGraph._ALL_DEPS[dep.modid] = node
                            continue
                        new_node = DependencyGraph.Node(dep_mod, node.graph)
                        DependencyGraph._ALL_DEPS[dep.modid] = new_node
                        node.graph.nodes.append(new_node)
                        process_node(new_node)

                for dep in mod.dependencies:
                    if dep.modid in ['forge', 'minecraft']:
                        continue
                    # if mod hasn't been processed and mod exists:
                    if dep.required and not dep.modid in DependencyGraph._ALL_DEPS and dep.modid in self.mods:
                        dep_mod = self.mods[dep.modid]
                        # mods with circular dependencies are collapsed into a single node (unlikely but possible)
                        if mod.modid in [x.modid for x in dep_mod.dependencies]:
                            node.mod_list.append(dep_mod)
                            DependencyGraph._ALL_DEPS[dep.modid] = node
                            continue
                        new_node = DependencyGraph.Node(dep_mod, node.graph)
                        DependencyGraph._ALL_DEPS[dep.modid] = new_node
                        node.graph.nodes.append(new_node)
                        process_node(new_node)

        for graph in graphs:
            process_node(graph.nodes[0])
            DependencyGraph._ALL_DEPS[graph.nodes[0].mod_list[0].modid] = graph.nodes[0]

        graph_set: List[DependencyGraph] = []
        for node in DependencyGraph._ALL_DEPS.values():
            if not node.graph in graph_set:
                graph_set.append(node.graph)
        print(f'total separate graphs: {len(graph_set)}')

        for i, graph in enumerate(graph_set):
            print('==================================')
            print(f'Graph {i}:')
            for node in graph.nodes:
                for mod in node.mod_list:
                    print(f" -> '{mod.modid}'")
            print()

        missing_count = 0
        for modid in self.mods.keys():
            if not modid in DependencyGraph._ALL_DEPS.keys():
                missing_count += 1
                print(f'Missing graph for mod "{self.mods[modid].name}" ({modid})')
        print(f'Missing graphs for {missing_count} mods')


        assert self.directory.has("logs"), "'logs' directory not found! Please run profile at least once!"
        logs = DirectoryReal(self.directory, "logs")

        error_files = ['latest.log', 'debug.log', 'latest_stdout.log']
        search_filename = ''
        for potential in error_files:
            if logs.has(potential) and error in FileReal(logs, potential).read().decode(errors="ignore"):
                search_filename = potential

        if search_filename:
            print(f'Scanning "{search_filename}"')
        else:
            print('Scanning all')

        # TODO: Determine which graph is causing the provided error by disabling half the remaining graphs
        # each time until a single graph is left
            
        # TODO: Sort the remaining graph, then disable the leaves, and iterate to each of the parents if
        # all of that parent's children have been visited

        return True

