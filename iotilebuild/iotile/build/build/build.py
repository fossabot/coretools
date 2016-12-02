# This file is adapted from python code released by WellDone International
# under the terms of the LGPLv3.  WellDone International's contact information is
# info@welldone.org
# http://welldone.org
#
# Modifications to this file from the original created at WellDone International 
# are copyright Arch Systems Inc.

#build.py
#Return the build settings json file.

import json as json
from iotile.core.utilities import deprecated
from iotile.core.dev.iotileobj import IOTile
import sys
from iotile.core.utilities.typedargs.annotate import *
from iotile.core.exceptions import *
from collections import namedtuple
from copy import deepcopy
import itertools
import os
import subprocess
import platform
from cStringIO import StringIO
import re
import os
from pkg_resources import resource_filename, Requirement

@takes_cmdline
def build(args):
    """
    Invoke the scons build system from the current directory, exactly as if 
    the scons tool had been invoked. 
    """

    # Do some sluething work to find scons if it's not installed into an importable
    # place, as it is usually not.
    try:
        import SCons.Script
    except ImportError:
        find_scons()
        import SCons.Script


    site_tools = os.path.join(resource_filename(Requirement.parse("iotile-build"), "iotile/build/config"), 'site_scons')
    site_path = os.path.abspath(site_tools)

    all_args = ['iotile', '--site-dir=%s' % site_path, '-Q']
    sys.argv = all_args + list(args)
    SCons.Script.main()

def find_scons():
    """
    Find the installed scons directory and add it to sys.path so we can import it
    """

    try:
        scons_path = find_executable('scons')

        p = subprocess.Popen([sys.executable, scons_path, '--version'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        output, output_err = p.communicate()
    except OSError:
        raise BuildError("Could not find an installed version of SCons.  SCons is required for the build system to work.")

    match = re.search("engine path: \['(.*)'\]", output)
    if match is None:
        raise BuildError("SCons version unsupported, it returned an unknown format for scons --version", output=output)

    install_dir = match.group(1)
    if not os.path.isdir(install_dir):
        raise BuildError("scons --version output invalid, listed engine directory does not exist", output=output, engine_dir=install_dir)

    libpath = os.path.dirname(install_dir)
    sys.path = sys.path + [libpath]

def find_executable(name):
    ext = ['.py', '']

    if platform.system()== 'Windows':
        ext += ['.exe']

    pathvars = os.environ['PATH']

    if platform.system() == 'Windows':
        sep = ';'
    else:
        sep = ':'

    paths = pathvars.split(sep)

    for p in paths:
        for e in ext:
            binpath = os.path.abspath(os.path.join(p, name + e))
            if os.path.exists(binpath):
                return binpath

    raise BuildError("Could not find an installed version of SCons.  SCons is required for the build system to work.", searched_paths = os.environ['PATH'])

def build_other(directory, artifacts=[]):
    """
    Invoke SCons to build a project in another directory. 

    All output is suppressed by default.
    """

    old_cwd = os.getcwd()

    try:
        os.chdir(directory)

        if isinstance(artifacts, basestring):
            if artifacts == "":
                artifacts = []
            else:
                artifacts = [artifacts]

        artifact_paths = [os.path.join('build', 'output', x) for x in artifacts]

        site_tools = os.path.join(resource_filename(Requirement.parse("iotile-build"), "iotile/build/config"), 'site_scons')
        site_path = os.path.abspath(site_tools)
        all_args = ['iotile', 'build'] + artifact_paths
        
        #Call this in a subprocess since SCons can't do repeated calls into SCons.Script.main()
        #because it sets global state about what nodes are present
        p = subprocess.Popen(all_args, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        output, output_err = p.communicate()

        return p.returncode, output, output_err
    finally:
        os.chdir(old_cwd)

def build_iotile(iotile, artifacts=[]):
    """
    Build all products in an IOTile 
    """

    #If there's no SConstruct then there's nothing to build
    buildfile = os.path.join(iotile.folder, 'SConstruct')
    if not os.path.exists(buildfile):
        return

    retval, stdout, stderr = build_other(iotile.folder)
    if retval != 0:
        print '*** START BUILD ERROR OUTPUT ***'
        print stderr
        print '*** END BUILD ERROR OUTPUT ***'

        raise BuildError('Error building IOTile', name=iotile.name, path=iotile.folder)


def merge_dicts(a, b):
    "merges b into a"

    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                merge_dicts(a[key], b[key])
            else:
                a[key] = b[key]
        else:
            a[key] = b[key]

    return a

MISSING = object()

ModuleSettings = namedtuple('ModuleSettings', ['overlays', 'settings'])

class TargetSettings (object):
    """
    A class that contains a dictionary of all the settings defined for
    a given chip in a ChipFamily.  The settings are a combination of
    default settings for the family which can be overwritten by chip
    specific settings.
    """

    def __init__(self, name, settings, family):
        self.name = name
        self.settings = settings
        self.family = family

    def output_name(self):
        return self.name.replace('/', '_').replace(":", "_")

    def arch_name(self):
        mod, arch = self.name.split(':')
        return arch.replace('/', "_")

    def arch_list(self):
        return self.name.split(':')[1]

    def archs(self, as_list=False):
        """
        Return a set containing all of the architectures used in this TargetSettings
        object.
        """

        archs = self.arch_list().split('/')
        
        if as_list:
            return archs

        return set(archs)

    def module_name(self):
        """
        Return the module name used to produce this TargetSettings object
        """

        name = self.name.split(':')[0]
        return name

    def retarget(self, remove=[], add=[]):
        """
        Return a TargetSettings object for the same module but with some of the architectures
        removed and others added.
        """

        archs = self.arch_list().split('/')

        for r in remove:
            if r in archs:
                archs.remove(r)

        archs.extend(add)

        archstr = "/".join(archs)
        return self.family.find(archstr, self.module_name())

    def build_dirs(self):
        """
        Return the build directory hierarchy:
        Defines:
        - build: build/chip
        - output: build/output
        - test: build/test/chip
        where chip is the cannonical name for the chip passed in
        """

        arch = self.arch_name()

        build = os.path.join('build', arch)
        output = os.path.join('build', 'output')
        test = os.path.join('build', 'test', arch)

        return {'build': build, 'output': output, 'test': test}

    def property(self, name, default=MISSING):
        """
        Get the value of the given property for this chip, using the default
        value if not found and one is provided.  If not found and default is None,
        raise an Exception.
        """

        if name in self.settings:
            return self.settings[name]  
        
        if default is not MISSING:
            return default

        raise ArgumentError("property %s not found for target '%s' and no default given" % (name, self.name))

    def combined_properties(self, suffix):
        """
        Get the value of all properties whose name ends with suffix and join them
        together into a list.
        """

        props = [y for x,y in self.settings.iteritems() if x.endswith(suffix)]
        properties = itertools.chain(*props)

        processed_props = [x for x in properties]
        return processed_props

    def includes(self):
        """
        Return all of the include directories for this chip as a list.
        """
        
        incs = self.combined_properties('includes')

        processed_incs = []
        for prop in incs:
            if isinstance(prop, basestring):
                processed_incs.append(prop)
            else:
                processed_incs.append(os.path.join(*prop))
        
        #All inclue paths are relative to base directory of the 
        fullpaths = [os.path.normpath(os.path.join('.', x)) for x in processed_incs]
        fullpaths.append(os.path.normpath(os.path.abspath(self.build_dirs()['build'])))

        return fullpaths

    def extra_sources(self):
        """
        If the architectures have specified that extra source files be included, return a list of paths to
        those source files.
        """

        raise BuildError("Extra sources no longer supported")
        paths = MomoPaths()
        base = paths.modules
        
        srcs = [y for x,y in self.settings.iteritems() if x.endswith('sources')]
        sources = itertools.chain(*srcs)

        fullpaths = [os.path.normpath(os.path.join(base, x)) for x in sources]
        return fullpaths

    def arch_prefixes(self):
        """
        Return the initial 1, 2, ..., N architectures as a prefix list

        For arch1/arch2/arch3, this returns
        [arch1],[arch1/arch2],[arch1/arch2/arch3]
        """

        archs = self.archs(as_list=True)
        prefixes = []

        for i in xrange(1, len(archs)+1):
            prefixes.append(archs[:i])

        return prefixes


class ArchitectureGroup:
    """A list of build architectures that may be used for building an IOTile Component.
    
    ArchitectureGroup objects are a collection of architectures, which are dictionaries
    that define properties relevant to buildign an IOTile Component.  Examples of these
    properties are: include paths, libraries, python proxy objects, etc.

    Whenever an IOTile component is built, it is always built targeting a list of 
    architectures, whose properties are then merged together to create the final
    dictionary of properties that is used to build the component.  
    """

    def __init__(self, modulefile):
        """Create an ArchitectureGroup from the dependencies and architectures in modulefile.
        """

        parent = os.path.dirname(modulefile)
        if parent is '':
            parent = '.'

        tile = IOTile(parent)

        with open(modulefile, 'rb') as fileobj:
            modsettings = json.load(fileobj)

        family = {}
        family['modules'] = {}
        family['module_targets'] = {}
        family['architectures'] = {}

        for dep in tile.dependencies:
            self._load_dependency(tile, dep, family)

        if "modules" in modsettings:
            merge_dicts(family['modules'], modsettings['modules'].copy())
        if "module_targets" in modsettings:
            merge_dicts(family['module_targets'], modsettings['module_targets'].copy())
        if "architectures" in modsettings:
            merge_dicts(family['architectures'], modsettings['architectures'].copy())

        #There is always a none architecture that doesn't have any settings.
        self.archs = {'none': {}}
        self.module_targets = {}
        self.modules = {}
        self.tile = tile

        self._load_architectures(family)
        self._load_module_targets(family)
        self._load_modules(family)

    @classmethod
    def _load_dependency(cls, tile, dep, family):
        """Load a dependency from build/deps/<unique_id>.
        """

        depfolder = dep['unique_id']
        deppath = os.path.join(tile.folder, 'build', 'deps', depfolder, 'module_settings.json')

        try:
            with open(deppath, "rb") as fileobj:
                deptile = json.load(fileobj)
        except IOError as e:
            raise BuildError("Could not find dependency", dependency=dep)
        if "architectures" in deptile:
            merge_dicts(family['architectures'], deptile['architectures'].copy())

    def find(self, name, module=None):
        """
        Given a target name and optionally a module name, return a settings object
        for that target
        """
        return self._load_target(name, module)

    def targets(self, module):
        """
        Return a sequence of all of the targets for the specified module.
        Modules that have no entry in module_targets in build_settings.json
        target all family defined targets by default.
        """

        if module in self.module_targets:
            return [self.find(x, module) for x in self.module_targets[module]]

        return [self.find(x, module) for x in self.known_targets.keys()]

    def for_all_targets(self, module, func, filter_func=None):
        """Call func once for all of the targets of this module.
        """

        for target in self.targets(module):
            if filter_func is None or filter_func(target):
                func(target)

    def validate_target(self, target):
        """
        Make sure that the specified target only contains architectures that we know about.
        """

        archs = target.split('/')

        for arch in archs:
            if not arch in self.archs:
                return False

        return True

    def _load_target(self, target, module=None):
        """
        Given a string specifying a series of architectural overlays as:
        <arch 1>/<arch 2>/... and optionally a module name to pull in
        module specific settings, return a TargetSettings object that
        encapsulates all of the settings for this target.
        """

        mod = ModuleSettings({}, {})
        if not self.validate_target(target):
            raise ArgumentError("Target %s is invalid, check to make sure every architecture in it is defined" % target)

        if module is not None:
            if module not in self.modules:
                raise ArgumentError("Unknown module name passed: %s" % module)

            mod = self.modules[module]

        settings = {}
        archs = target.split('/')

        for arch in archs:
            arch_settings = deepcopy(self.archs[arch])

            if arch in mod.overlays:
                arch_settings = merge_dicts(arch_settings, mod.overlays[arch])

            #Allow this architecture to overlay previous architectures as well
            if "overlays" in arch_settings:
                for arch2 in archs:
                    if arch2 == arch:
                        break

                    if arch2 in arch_settings["overlays"]:
                        arch_settings = merge_dicts(arch_settings, arch_settings["overlays"][arch2])

                del arch_settings["overlays"]

            settings = merge_dicts(settings, arch_settings)

        settings = merge_dicts(settings, mod.settings)

        targetname = "%s:%s" % (str(module), target)

        return TargetSettings(targetname, settings, self)

    def _load_module_targets(self, family):
        if "module_targets" in family:
            for mod, targets in family['module_targets'].iteritems():
                for target in targets:
                    if not self.validate_target(target):
                        raise InternalError("Module %s targets unknown architectures '%s'" % (mod, target))

                self.module_targets[mod] = targets

    def _load_architectures(self, family):
        """
        Load in all of the architectural overlays for this family.  An architecture adds configuration
        information that is used to build a common set of source code for a particular hardware and sitation.
        They are stackable so that you can specify a chip and a configuration for that chip, for example.
        """

        if "architectures" not in family:
            raise InternalError("required architectures key not in build_settings.json for desired family")


        for key, val in family['architectures'].iteritems():
            if not isinstance(val, dict):
                raise InternalError("All entries under chip_settings must be dictionaries")

            self.archs[key] = deepcopy(val)

    def _load_modules(self, family):
        if "modules" not in family:
            raise InternalError("required modules key not in build_settings.json for desired family")

        for modname in family['modules']:
            overlays = {}
            rawmod = family['modules'][modname]

            if 'overlays' in rawmod:
                overlays = rawmod['overlays']
                del rawmod['overlays']

            mod = ModuleSettings(overlays, rawmod)
            self.modules[modname] = mod
